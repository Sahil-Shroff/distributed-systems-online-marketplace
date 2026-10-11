import json
import os
import grpc
from concurrent import futures

# Add generated directory to sys.path
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'generated'))
# Ensure repo root is on path for server_side imports
from pathlib import Path
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from protos import database_pb2
from protos import database_pb2_grpc
from server_side.customer_db.backends.sqlite import CUSTOMER_SQLITE_SCHEMA, SQLiteCustomerRepository, SQLiteIdAllocator
from server_side.customer_db.models import SESSION_TTL
from server_side.customer_db.operations import Operation
from server_side.customer_db.replication.runtime import CustomerDbReplicationRuntime
from server_side.customer_db.service import AuthenticationError, CustomerDbService, SessionError
from server_side.data_access_layer.db import Database_Connection
from server_side.sqlite_schemas import CUSTOMER_SQLITE_DEFAULT_DB, PRODUCT_SQLITE_DEFAULT_DB, PRODUCT_SQLITE_SCHEMA

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

class DatabaseServiceServicer(database_pb2_grpc.DatabaseServiceServicer):
    def __init__(self):
        self.customer_db = Database_Connection(
            os.getenv("CUSTOMER_DB_NAME", CUSTOMER_SQLITE_DEFAULT_DB),
            db_path=os.getenv("CUSTOMER_DB_PATH"),
            init_schema=CUSTOMER_SQLITE_SCHEMA,
        )
        self.product_db = Database_Connection(
            os.getenv("PRODUCT_DB_NAME", PRODUCT_SQLITE_DEFAULT_DB),
            db_path=os.getenv("PRODUCT_DB_PATH"),
            init_schema=PRODUCT_SQLITE_SCHEMA,
        )
        self.customer_repo = SQLiteCustomerRepository(self.customer_db)
        self.customer_service = CustomerDbService(
            repository=self.customer_repo,
            allocator=SQLiteIdAllocator(self.customer_db),
        )
        self.customer_replication = CustomerDbReplicationRuntime.from_env(
            apply_callback=self.customer_service.apply_replicated,
        )
        if self.customer_replication is not None:
            self.customer_replication.start()

    def _apply_customer_operation(self, operation: Operation) -> None:
        if self.customer_replication is not None:
            timeout_seconds = float(os.getenv("CUSTOMER_DB_REPLICATION_DELIVERY_TIMEOUT", "5.0"))
            self.customer_replication.submit(operation, timeout=timeout_seconds)
            return
        self.customer_service.apply_replicated(operation)

    # --- Account / Session Operations ---
    def CreateAccount(self, request, context):
        try:
            if request.role == "buyer":
                operation = self.customer_service.build_create_buyer(request.username, request.password)
                self._apply_customer_operation(operation)
                user_id = operation.buyer_id
            else:
                operation = self.customer_service.build_create_seller(request.username, request.password)
                self._apply_customer_operation(operation)
                user_id = operation.seller_id
            return database_pb2.CreateAccountResponse(user_id=user_id)
        except TimeoutError as e:
            context.abort(grpc.StatusCode.DEADLINE_EXCEEDED, str(e))
        except Exception as e:
            context.abort(grpc.StatusCode.ALREADY_EXISTS, str(e))

    def AuthenticateUser(self, request, context):
        try:
            if request.role == "buyer":
                buyer = self.customer_repo.get_buyer_by_username_password(request.username, request.password)
                if buyer is None:
                    raise AuthenticationError("Invalid username or password")
                operation = self.customer_service.build_create_session(role="buyer", user_id=buyer.buyer_id)
                self._apply_customer_operation(operation)
                return database_pb2.AuthenticateResponse(user_id=buyer.buyer_id, session_id=operation.session_id)
            seller = self.customer_repo.get_seller_by_username_password(request.username, request.password)
            if seller is None:
                raise AuthenticationError("Invalid username or password")
            operation = self.customer_service.build_create_session(role="seller", user_id=seller.seller_id)
            self._apply_customer_operation(operation)
            return database_pb2.AuthenticateResponse(user_id=seller.seller_id, session_id=operation.session_id)
        except AuthenticationError as e:
            context.abort(grpc.StatusCode.UNAUTHENTICATED, str(e))
        except TimeoutError as e:
            context.abort(grpc.StatusCode.DEADLINE_EXCEEDED, str(e))

    def VerifySession(self, request, context):
        try:
            observed_at = self.customer_service.clock.now()
            session = self.customer_repo.get_session(request.session_id)
            if session is None or session.last_access_timestamp <= observed_at - SESSION_TTL:
                raise SessionError("Session invalid or expired")
            operation = self.customer_service.build_touch_session(request.session_id, touched_at=observed_at)
            self._apply_customer_operation(operation)
            refreshed = self.customer_repo.get_session(request.session_id)
            if refreshed is None:
                raise SessionError("Session invalid or expired")
            return database_pb2.VerifySessionResponse(
                user_id=refreshed.user_id,
                role=refreshed.role,
            )
        except SessionError as e:
            context.abort(grpc.StatusCode.UNAUTHENTICATED, str(e))
        except TimeoutError as e:
            context.abort(grpc.StatusCode.DEADLINE_EXCEEDED, str(e))

    def DeleteSessions(self, request, context):
        if request.scope == "all":
            operation = self.customer_service.build_delete_sessions_for_user_role(
                user_id=request.user_id,
                role=request.role,
            )
        else:
            operation = self.customer_service.build_delete_session(request.session_id)
        try:
            self._apply_customer_operation(operation)
        except TimeoutError as e:
            context.abort(grpc.StatusCode.DEADLINE_EXCEEDED, str(e))
        return database_pb2.Empty()

    # --- Item Operations ---
    def SearchItems(self, request, context):
        query = "SELECT item_id, item_name, category, keywords, condition_is_new, sale_price, quantity, seller_id FROM items WHERE quantity > 0"
        params = []

        if request.category != 0:
            query += " AND category = %s"
            params.append(request.category)

        rows = self.product_db.execute(query, tuple(params), fetch=True) or []
        items = []
        for row in rows:
            item = self._item_from_row(row)
            if request.keywords and not set(item.keywords).intersection(request.keywords):
                continue
            items.append(item)
        return database_pb2.SearchItemsResponse(items=items)

    def GetItem(self, request, context):
        rows = self.product_db.execute(
            "SELECT item_id, item_name, category, keywords, condition_is_new, sale_price, quantity, seller_id FROM items WHERE item_id = %s",
            (request.item_id,),
            fetch=True
        )
        if not rows:
            context.abort(grpc.StatusCode.NOT_FOUND, "Item not found")
        return self._item_from_row(rows[0])

    def RegisterItem(self, request, context):
        condition_is_new = request.condition.lower() in ("new", "brand new", "mint")
        rows = self.product_db.execute(
            """
            INSERT INTO items (item_name, category, keywords, condition_is_new, sale_price, quantity, seller_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING item_id
            """,
            (
                request.item_name,
                request.category,
                self._encode_keywords(list(request.keywords)),
                condition_is_new,
                request.price,
                request.quantity,
                request.seller_id,
            ),
            fetch=True
        )
        item_id = rows[0][0] if rows else 0
        return database_pb2.RegisterItemResponse(item_id=item_id)

    def UpdateItemPrice(self, request, context):
        rows = self.product_db.execute(
            "UPDATE items SET sale_price = %s WHERE item_id = %s AND seller_id = %s RETURNING item_id",
            (request.price, request.item_id, request.seller_id),
            fetch=True
        )
        if not rows:
            context.abort(grpc.StatusCode.NOT_FOUND, "Item not found or unauthorized")
        return database_pb2.Empty()

    def UpdateItemQuantity(self, request, context):
        rows = self.product_db.execute(
            "SELECT quantity FROM items WHERE item_id = %s AND seller_id = %s",
            (request.item_id, request.seller_id),
            fetch=True
        )
        if not rows:
            context.abort(grpc.StatusCode.NOT_FOUND, "Item not found or unauthorized")
            
        current_qty = rows[0][0]
        new_qty = current_qty - request.quantity_delta
        if new_qty < 0:
            context.abort(grpc.StatusCode.FAILED_PRECONDITION, "Insufficient quantity")
            
        self.product_db.execute(
            "UPDATE items SET quantity = %s WHERE item_id = %s AND seller_id = %s",
            (new_qty, request.item_id, request.seller_id),
            fetch=False
        )
        return database_pb2.UpdateItemQuantityResponse(new_quantity=new_qty)

    def GetItemsBySeller(self, request, context):
        rows = self.product_db.execute(
            "SELECT item_id, item_name, category, keywords, condition_is_new, sale_price, quantity, seller_id FROM items WHERE seller_id = %s",
            (request.seller_id,),
            fetch=True
        ) or []
        items = []
        for r in rows:
            items.append(self._item_from_row(r))
        return database_pb2.SearchItemsResponse(items=items)

    # --- Cart Operations ---
    def AddToCart(self, request, context):
        self.product_db.execute(
            """
            INSERT INTO cart_items (buyer_id, session_id, item_id, quantity, is_saved)
            VALUES (%s, %s, %s, %s, FALSE)
            ON CONFLICT (buyer_id, session_id, item_id, is_saved) DO UPDATE 
            SET quantity = cart_items.quantity + EXCLUDED.quantity
            """,
            (request.buyer_id, request.session_id, request.item_id, request.quantity),
            fetch=False
        )
        return database_pb2.Empty()

    def RemoveFromCart(self, request, context):
        self.product_db.execute(
            "DELETE FROM cart_items WHERE buyer_id = %s AND session_id = %s AND item_id = %s AND is_saved = FALSE",
            (request.buyer_id, request.session_id, request.item_id),
            fetch=False
        )
        return database_pb2.Empty()

    def GetCartItemQuantity(self, request, context):
        row = self.product_db.execute(
            "SELECT quantity FROM cart_items WHERE buyer_id = %s AND session_id = %s AND item_id = %s AND is_saved = FALSE",
            (request.buyer_id, request.session_id, request.item_id),
            fetch=True
        )
        qty = row[0][0] if row else 0
        return database_pb2.QuantityResponse(quantity=qty)

    def UpdateCartItem(self, request, context):
        if request.quantity <= 0:
            self.product_db.execute(
                "DELETE FROM cart_items WHERE buyer_id = %s AND session_id = %s AND item_id = %s AND is_saved = FALSE",
                (request.buyer_id, request.session_id, request.item_id),
                fetch=False
            )
        else:
            self.product_db.execute(
                "UPDATE cart_items SET quantity = %s WHERE buyer_id = %s AND session_id = %s AND item_id = %s AND is_saved = FALSE",
                (request.quantity, request.buyer_id, request.session_id, request.item_id),
                fetch=False
            )
        return database_pb2.Empty()

    def SaveCart(self, request, context):
        # Move this session's cart to the shared saved cart (session_id='')
        self.product_db.execute(
            """
            INSERT INTO cart_items (buyer_id, session_id, item_id, quantity, is_saved)
            SELECT buyer_id, '', item_id, quantity, TRUE
            FROM cart_items
            WHERE buyer_id = %s AND session_id = %s AND is_saved = FALSE
            ON CONFLICT (buyer_id, session_id, item_id, is_saved)
            DO UPDATE SET quantity = cart_items.quantity + EXCLUDED.quantity
            """,
            (request.buyer_id, request.session_id),
            fetch=False
        )
        # Clear all unsaved carts for this buyer across every session
        self.product_db.execute(
            "DELETE FROM cart_items WHERE buyer_id = %s AND is_saved = FALSE",
            (request.buyer_id,),
            fetch=False
        )
        return database_pb2.Empty()

    def ClearCart(self, request, context):
        self.product_db.execute(
            "DELETE FROM cart_items WHERE buyer_id = %s AND session_id = %s AND is_saved = FALSE",
            (request.buyer_id, request.session_id),
            fetch=False
        )
        return database_pb2.Empty()

    def ListCart(self, request, context):
        rows = self.product_db.execute(
            "SELECT item_id, quantity FROM cart_items WHERE buyer_id = %s AND session_id = %s AND is_saved = FALSE",
            (request.buyer_id, request.session_id),
            fetch=True
        ) or []
        items = [database_pb2.CartItem(item_id=r[0], quantity=r[1]) for r in rows]
        return database_pb2.CartListResponse(items=items)

    def DeleteUnsavedCart(self, request, context):
        self.product_db.execute(
            "DELETE FROM cart_items WHERE buyer_id = %s AND session_id = %s AND is_saved = FALSE",
            (request.buyer_id, request.session_id),
            fetch=False
        )
        return database_pb2.Empty()

    def ListSavedCart(self, request, context):
        rows = self.product_db.execute(
            "SELECT item_id, quantity FROM cart_items WHERE buyer_id = %s AND is_saved = TRUE",
            (request.buyer_id,),
            fetch=True
        ) or []
        items = [database_pb2.CartItem(item_id=r[0], quantity=r[1]) for r in rows]
        return database_pb2.CartListResponse(items=items)

    def ClearSavedCart(self, request, context):
        self.product_db.execute(
            "DELETE FROM cart_items WHERE buyer_id = %s AND is_saved = TRUE",
            (request.buyer_id,),
            fetch=False
        )
        return database_pb2.Empty()

    # --- Feedback / Rating ---
    def ProvideFeedback(self, request, context):
        rows = self.product_db.execute("SELECT seller_id FROM items WHERE item_id = %s", (request.item_id,), fetch=True)
        if not rows:
            context.abort(grpc.StatusCode.NOT_FOUND, "Item not found")
        seller_id = rows[0][0]

        feedback_row = self.product_db.execute(
            "SELECT item_feedback FROM items WHERE item_id = %s",
            (request.item_id,),
            fetch=True,
        )
        feedback = json.loads(feedback_row[0][0]) if feedback_row and feedback_row[0][0] else [0, 0]
        if request.is_positive:
            feedback[0] += 1
        else:
            feedback[1] += 1
        self.product_db.execute(
            "UPDATE items SET item_feedback = %s WHERE item_id = %s",
            (json.dumps(feedback), request.item_id),
            fetch=False,
        )
        operation = self.customer_service.build_update_seller_feedback(
            seller_id=seller_id,
            is_positive=request.is_positive,
        )
        try:
            self._apply_customer_operation(operation)
        except TimeoutError as e:
            context.abort(grpc.StatusCode.DEADLINE_EXCEEDED, str(e))
        return database_pb2.Empty()

    def GetSellerRating(self, request, context):
        feedback = self.customer_service.get_seller_feedback_counts(request.seller_id)
        if feedback is None:
            return database_pb2.SellerRatingResponse(pos=0, neg=0)
        return database_pb2.SellerRatingResponse(pos=feedback[0], neg=feedback[1])

    def RecordSellerFeedback(self, request, context):
        operation = self.customer_service.build_update_seller_feedback(
            seller_id=request.seller_id,
            is_positive=request.is_positive,
        )
        try:
            self._apply_customer_operation(operation)
        except TimeoutError as e:
            context.abort(grpc.StatusCode.DEADLINE_EXCEEDED, str(e))
        return database_pb2.Empty()

    # --- Purchases ---
    def GetPurchaseHistory(self, request, context):
        rows = self.product_db.execute(
            "SELECT item_id, quantity, purchased_at FROM purchases WHERE buyer_id = %s",
            (request.buyer_id,),
            fetch=True
        ) or []
        records = [database_pb2.PurchaseRecord(item_id=r[0], quantity=r[1], purchased_at=str(r[2])) for r in rows]
        return database_pb2.PurchaseHistoryResponse(records=records)

    def CreatePurchase(self, request, context):
        self.product_db.execute(
            "INSERT INTO purchases (buyer_id, item_id, quantity) VALUES (%s, %s, %s)",
            (request.buyer_id, request.item_id, request.quantity),
            fetch=False
        )
        # Find seller
        rows = self.product_db.execute("SELECT seller_id FROM items WHERE item_id = %s", (request.item_id,), fetch=True)
        if rows:
            seller_id = rows[0][0]
            operation = self.customer_service.build_complete_purchase(
                buyer_id=request.buyer_id,
                seller_id=seller_id,
                quantity=request.quantity,
            )
            try:
                self._apply_customer_operation(operation)
            except TimeoutError as e:
                context.abort(grpc.StatusCode.DEADLINE_EXCEEDED, str(e))
        return database_pb2.Empty()

    def RecordPurchaseStats(self, request, context):
        operation = self.customer_service.build_complete_purchase(
            buyer_id=request.buyer_id,
            seller_id=request.seller_id,
            quantity=request.quantity,
        )
        try:
            self._apply_customer_operation(operation)
        except TimeoutError as e:
            context.abort(grpc.StatusCode.DEADLINE_EXCEEDED, str(e))
        return database_pb2.Empty()

    def _item_from_row(self, row):
        return database_pb2.Item(
            item_id=row[0],
            item_name=row[1],
            category=row[2],
            keywords=self._decode_keywords(row[3]),
            condition_is_new=bool(row[4]),
            price=float(row[5]),
            quantity=row[6],
            seller_id=row[7],
        )

    def _encode_keywords(self, keywords):
        return json.dumps(keywords)

    def _decode_keywords(self, raw_keywords):
        return list(json.loads(raw_keywords)) if raw_keywords else []

def serve():
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    database_pb2_grpc.add_DatabaseServiceServicer_to_server(DatabaseServiceServicer(), server)
    port = os.getenv("DB_SERVICE_PORT", "50051")
    bind_addr = os.getenv("DB_SERVICE_BIND", f"0.0.0.0:{port}")
    server.add_insecure_port(bind_addr)
    print(f"Database gRPC Service starting on {bind_addr}...")
    server.start()
    server.wait_for_termination()

if __name__ == '__main__':
    serve()
