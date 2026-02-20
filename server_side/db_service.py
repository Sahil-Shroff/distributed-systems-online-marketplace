import os
import grpc
from concurrent import futures
import time

# Add generated directory to sys.path
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'generated'))

from protos import database_pb2
from protos import database_pb2_grpc
from server_side.data_access_layer.db import Database_Connection

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

class DatabaseServiceServicer(database_pb2_grpc.DatabaseServiceServicer):
    def __init__(self):
        self.customer_db = Database_Connection(os.getenv("CUSTOMER_DB_NAME", "customer_db"))
        self.product_db = Database_Connection(os.getenv("PRODUCT_DB_NAME", "product_db"))

    # --- Account / Session Operations ---
    def CreateAccount(self, request, context):
        table = "buyers" if request.role == "buyer" else "sellers"
        id_col = "buyer_id" if request.role == "buyer" else "seller_id"
        
        try:
            rows = self.customer_db.execute(
                f"INSERT INTO {table} (username, password) VALUES (%s, %s) RETURNING {id_col}",
                (request.username, request.password),
                fetch=True
            )
            user_id = rows[0][0] if rows else 0
            return database_pb2.CreateAccountResponse(user_id=user_id)
        except Exception as e:
            context.abort(grpc.StatusCode.ALREADY_EXISTS, str(e))

    def AuthenticateUser(self, request, context):
        table = "buyers" if request.role == "buyer" else "sellers"
        id_col = "buyer_id" if request.role == "buyer" else "seller_id"
        
        rows = self.customer_db.execute(
            f"SELECT {id_col} FROM {table} WHERE username = %s AND password = %s",
            (request.username, request.password),
            fetch=True
        )
        if not rows:
            context.abort(grpc.StatusCode.UNAUTHENTICATED, "Invalid username or password")
            
        user_id = rows[0][0]
        
        # Create session
        self.customer_db.execute(
            "INSERT INTO sessions (role, user_id, last_access_timestamp) VALUES (%s, %s, NOW())",
            (request.role, user_id),
            fetch=False
        )
        
        rows = self.customer_db.execute(
            "SELECT session_id FROM sessions WHERE role = %s AND user_id = %s ORDER BY last_access_timestamp DESC LIMIT 1",
            (request.role, user_id),
            fetch=True
        )
        session_id = str(rows[0][0]) if rows else ""
        return database_pb2.AuthenticateResponse(user_id=user_id, session_id=session_id)

    def VerifySession(self, request, context):
        # Atomic Touch Logic from PA1
        rows = self.customer_db.execute(
            """
            UPDATE sessions 
            SET last_access_timestamp = NOW() 
            WHERE session_id = %s 
              AND last_access_timestamp > NOW() - INTERVAL '5 minutes'
            RETURNING user_id, role
            """,
            (request.session_id,),
            fetch=True
        )
        if not rows:
            context.abort(grpc.StatusCode.UNAUTHENTICATED, "Session invalid or expired")
            
        user_id, role = rows[0]
        return database_pb2.VerifySessionResponse(user_id=user_id, role=role)

    def DeleteSessions(self, request, context):
        if request.scope == "all":
            self.customer_db.execute(
                "DELETE FROM sessions WHERE user_id = %s AND role = %s",
                (request.user_id, request.role),
                fetch=False
            )
        else:
            self.customer_db.execute(
                "DELETE FROM sessions WHERE session_id = %s",
                (request.session_id,),
                fetch=False
            )
        return database_pb2.Empty()

    # --- Item Operations ---
    def SearchItems(self, request, context):
        query = "SELECT item_id, item_name, category, keywords, condition_is_new, sale_price, quantity, seller_id FROM items WHERE quantity > 0"
        params = []
        
        if request.category != 0:
            query += " AND category = %s"
            params.append(request.category)
            
        if request.keywords:
            # Better Search Semantics: matches ANY of the keywords
            query += " AND keywords && %s"
            params.append(list(request.keywords))
            
        rows = self.product_db.execute(query, tuple(params), fetch=True) or []
        items = []
        for r in rows:
            items.append(database_pb2.Item(
                item_id=r[0], item_name=r[1], category=r[2], keywords=r[3],
                condition_is_new=r[4], price=float(r[5]), quantity=r[6], seller_id=r[7]
            ))
        return database_pb2.SearchItemsResponse(items=items)

    def GetItem(self, request, context):
        rows = self.product_db.execute(
            "SELECT item_id, item_name, category, keywords, condition_is_new, sale_price, quantity, seller_id FROM items WHERE item_id = %s",
            (request.item_id,),
            fetch=True
        )
        if not rows:
            context.abort(grpc.StatusCode.NOT_FOUND, "Item not found")
        r = rows[0]
        return database_pb2.Item(
            item_id=r[0], item_name=r[1], category=r[2], keywords=r[3],
            condition_is_new=r[4], price=float(r[5]), quantity=r[6], seller_id=r[7]
        )

    def RegisterItem(self, request, context):
        condition_is_new = request.condition.lower() in ("new", "brand new", "mint")
        rows = self.product_db.execute(
            """
            INSERT INTO items (item_name, category, keywords, condition_is_new, sale_price, quantity, seller_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING item_id
            """,
            (request.item_name, request.category, list(request.keywords), condition_is_new, request.price, request.quantity, request.seller_id),
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
        new_qty = current_qty + request.quantity_delta
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
            items.append(database_pb2.Item(
                item_id=r[0], item_name=r[1], category=r[2], keywords=r[3],
                condition_is_new=r[4], price=float(r[5]), quantity=r[6], seller_id=r[7]
            ))
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
        # Update Item Feedback
        col = "thumbs_up" if request.is_positive else "thumbs_down"
        # We need to find the seller_id first for the combined update or handle them separately
        rows = self.product_db.execute("SELECT seller_id FROM items WHERE item_id = %s", (request.item_id,), fetch=True)
        if not rows:
            context.abort(grpc.StatusCode.NOT_FOUND, "Item not found")
        seller_id = rows[0][0]
        
        # In this simplistic impl, let's assume item_feedback is a structured col or just increment it
        # Requirement: "Item feedback: <integer number of thumbs up, integer number of thumbs down>"
        # Assuming schema: item_feedback INTEGER[] DEFAULT ARRAY[0, 0]
        idx = 1 if request.is_positive else 2
        self.product_db.execute(
            f"UPDATE items SET item_feedback[{idx}] = item_feedback[{idx}] + 1 WHERE item_id = %s",
            (request.item_id,),
            fetch=False
        )
        
        # Requirement: "Seller feedback: <integer number of thumbs up, integer number of thumbs down>"
        self.customer_db.execute(
            f"UPDATE sellers SET seller_feedback[{idx}] = seller_feedback[{idx}] + 1 WHERE seller_id = %s",
            (seller_id,),
            fetch=False
        )
        return database_pb2.Empty()

    def GetSellerRating(self, request, context):
        rows = self.customer_db.execute(
            "SELECT seller_feedback FROM sellers WHERE seller_id = %s",
            (request.seller_id,),
            fetch=True
        )
        if not rows:
            return database_pb2.SellerRatingResponse(pos=0, neg=0)
        feedback = rows[0][0] # feedback is expected to be [pos, neg]
        return database_pb2.SellerRatingResponse(pos=feedback[0], neg=feedback[1])

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
        # Requirement: update items_purchased for buyer and items_sold for seller
        self.customer_db.execute(
            "UPDATE buyers SET items_purchased = items_purchased + %s WHERE buyer_id = %s",
            (request.quantity, request.buyer_id),
            fetch=False
        )
        # Find seller
        rows = self.product_db.execute("SELECT seller_id FROM items WHERE item_id = %s", (request.item_id,), fetch=True)
        if rows:
            seller_id = rows[0][0]
            self.customer_db.execute(
                "UPDATE sellers SET items_sold = items_sold + %s WHERE seller_id = %s",
                (request.quantity, seller_id),
                fetch=False
            )
        return database_pb2.Empty()

def serve():
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    database_pb2_grpc.add_DatabaseServiceServicer_to_server(DatabaseServiceServicer(), server)
    port = os.getenv("DB_SERVICE_PORT", "50051")
    server.add_insecure_port(f'[::]:{port}')
    print(f"Database gRPC Service starting on port {port}...")
    server.start()
    server.wait_for_termination()

if __name__ == '__main__':
    serve()
