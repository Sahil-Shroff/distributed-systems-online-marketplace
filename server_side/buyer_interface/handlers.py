import os
from typing import Any, Dict, Iterable, List

from server_side.data_access_layer.db import Database_Connection
from server_side.buyer_interface import buyer_repository as repo
from zeep import Client as SoapClient

# "single", "all" - determines whether logout invalidates only the current session or all sessions
LOGOUT_SCOPE = os.getenv("LOGOUT_SCOPE", "single").lower()
FINANCIAL_SERVICE_WSDL = os.getenv("FINANCIAL_SERVICE_WSDL", "http://localhost:8002/?wsdl")


# ---------- Common helpers ----------

def _get_db(dbs: Dict[str, Database_Connection], key: str) -> Database_Connection:
    db = dbs.get(key)
    if db is None:
        raise RuntimeError(f"{key} database connection is not configured")
    return db


def _require_fields(payload: Dict[str, Any], required: Iterable[str]):
    missing = [f for f in required if payload.get(f) is None]
    if missing:
        raise ValueError(f"Missing required fields: {', '.join(missing)}")


def _require_buyer_session(dbs: Dict[str, Database_Connection], session_id: str) -> int:
    if not session_id:
        raise ValueError("session_id required")
    customer_db = _get_db(dbs, "customer")
    row = repo.fetch_session(customer_db, session_id)
    if not row:
        raise ValueError("invalid session")
    user_id, role = row
    if isinstance(role, memoryview):
        role = role.tobytes()
    if isinstance(role, bytes):
        role = role.decode("utf-8")
    if role != "buyer":
        raise ValueError("invalid role for this operation")
    return user_id


# ---------- Account / Session ----------

def handle_create_account(request: Dict[str, Any], dbs: Dict[str, Database_Connection]) -> Dict[str, Any]:
    payload = request.get("payload", {})
    _require_fields(payload, ("username", "password"))
    username = payload["username"]
    password = payload["password"]

    customer_db = _get_db(dbs, "customer")
    buyer_id = repo.create_buyer(customer_db, username, password)
    return {"buyer_id": buyer_id}


def handle_login(request: Dict[str, Any], dbs: Dict[str, Database_Connection]) -> Dict[str, Any]:
    payload = request.get("payload", {})
    _require_fields(payload, ("username", "password"))
    username = payload["username"]
    password = payload["password"]

    customer_db = _get_db(dbs, "customer")
    buyer_id = repo.authenticate_buyer(customer_db, username, password)
    if buyer_id is None:
        raise ValueError("invalid username or password")

    session_id = repo.create_session(customer_db, buyer_id)
    return {"session_id": session_id, "buyer_id": buyer_id}


def handle_logout(request: Dict[str, Any], dbs: Dict[str, Database_Connection]) -> Dict[str, Any]:
    session_id = request.get("session_id")
    if not session_id:
        raise ValueError("session_id required for logout")

    customer_db = _get_db(dbs, "customer")
    row = repo.fetch_session(customer_db, session_id)
    if not row:
        return {"status": "success"}  # idempotent
    user_id, role = row
    if role != "buyer":
        raise ValueError("invalid role for logout")

    product_db = _get_db(dbs, "product")
    repo.delete_unsaved_cart(product_db, user_id, session_id)

    repo.delete_sessions(customer_db, session_id, user_id, role, LOGOUT_SCOPE)
    return {"status": "success", "scope": LOGOUT_SCOPE}


# ---------- Item browsing ----------

def handle_search_items_for_sale(request: Dict[str, Any], dbs: Dict[str, Database_Connection]) -> Dict[str, Any]:
    payload = request.get("payload", {})
    category = payload.get("category")
    keywords: List[str] = payload.get("keywords", [])
    session_id = request.get("session_id")
    _require_buyer_session(dbs, session_id)

    product_db = _get_db(dbs, "product")
    rows = repo.search_items(product_db, category, keywords)
    items = [
        {
            "item_id": r[0],
            "item_name": r[1],
            "category": r[2],
            "keywords": r[3],
            "condition_is_new": r[4],
            "price": float(r[5]) if r[5] is not None else None,
            "quantity": r[6],
            "seller_id": r[7],
        }
        for r in rows
    ]
    return {"items": items}


def handle_get_item(request: Dict[str, Any], dbs: Dict[str, Database_Connection]) -> Dict[str, Any]:
    payload = request.get("payload", {})
    _require_fields(payload, ("item_id",))
    item_id = payload["item_id"]
    session_id = request.get("session_id")
    _require_buyer_session(dbs, session_id)

    product_db = _get_db(dbs, "product")
    row = repo.get_item(product_db, item_id)
    if not row:
        raise ValueError("item not found")
    return {
        "item_id": row[0],
        "item_name": row[1],
        "category": row[2],
        "keywords": row[3],
        "condition_is_new": row[4],
        "price": float(row[5]) if row[5] is not None else None,
        "quantity": row[6],
        "seller_id": row[7],
    }


# ---------- Cart operations ----------

def handle_add_item_to_cart(request: Dict[str, Any], dbs: Dict[str, Database_Connection]) -> Dict[str, Any]:
    payload = request.get("payload", {})
    _require_fields(payload, ("item_id", "quantity"))
    item_id = payload["item_id"]
    qty = payload["quantity"]
    session_id = request.get("session_id")
    buyer_id = _require_buyer_session(dbs, session_id)
    session_id_str = str(session_id)

    product_db = _get_db(dbs, "product")
    available = repo.get_item_stock(product_db, item_id)
    if available is None:
        raise ValueError("item not found")
    if qty > available:
        raise ValueError("ITEM_OUT_OF_STOCK")

    repo.add_item_to_cart(product_db, buyer_id, session_id_str, item_id, qty)
    return {"status": "success"}


def handle_remove_item_from_cart(request: Dict[str, Any], dbs: Dict[str, Database_Connection]) -> Dict[str, Any]:
    payload = request.get("payload", {})
    _require_fields(payload, ("item_id", "quantity"))
    item_id = payload["item_id"]
    qty = payload["quantity"]
    session_id = request.get("session_id")
    buyer_id = _require_buyer_session(dbs, session_id)
    session_id_str = str(session_id)

    product_db = _get_db(dbs, "product")
    current = repo.get_cart_item_quantity(product_db, buyer_id, session_id_str, item_id)
    if current is None:
        raise ValueError("item not in cart")
    new_qty = current - qty
    repo.update_cart_item(product_db, buyer_id, session_id_str, item_id, new_qty)
    return {"status": "success", "quantity": max(new_qty, 0)}


def handle_save_cart(request: Dict[str, Any], dbs: Dict[str, Database_Connection]) -> Dict[str, Any]:
    session_id = request.get("session_id")
    buyer_id = _require_buyer_session(dbs, session_id)
    session_id_str = str(session_id)
    product_db = _get_db(dbs, "product")
    repo.save_cart(product_db, buyer_id, session_id_str)
    return {"status": "success"}


def handle_clear_cart(request: Dict[str, Any], dbs: Dict[str, Database_Connection]) -> Dict[str, Any]:
    session_id = request.get("session_id")
    buyer_id = _require_buyer_session(dbs, session_id)
    session_id_str = str(session_id)
    product_db = _get_db(dbs, "product")
    repo.clear_cart(product_db, buyer_id, session_id_str)
    return {"status": "success"}


def handle_display_cart(request: Dict[str, Any], dbs: Dict[str, Database_Connection]) -> Dict[str, Any]:
    session_id = request.get("session_id")
    buyer_id = _require_buyer_session(dbs, session_id)
    session_id_str = str(session_id)
    product_db = _get_db(dbs, "product")
    rows = repo.list_cart(product_db, buyer_id, session_id_str)
    items = [{"item_id": r[0], "quantity": r[1]} for r in rows]
    return {"cart": items}


# ---------- Feedback and ratings ----------

def handle_provide_feedback(request: Dict[str, Any], dbs: Dict[str, Database_Connection]) -> Dict[str, Any]:
    payload = request.get("payload", {})
    if "thumbs_up" in payload:
        payload["is_positive"] = payload["thumbs_up"]
    _require_fields(payload, ("item_id", "is_positive"))
    item_id = payload["item_id"]
    is_positive = bool(payload["is_positive"])
    session_id = request.get("session_id")
    buyer_id = _require_buyer_session(dbs, session_id)

    product_db = _get_db(dbs, "product")
    customer_db = _get_db(dbs, "customer")
    repo.provide_feedback(product_db, customer_db, item_id, buyer_id, is_positive)
    return {"status": "success"}


def handle_get_seller_rating(request: Dict[str, Any], dbs: Dict[str, Database_Connection]) -> Dict[str, Any]:
    payload = request.get("payload", {})
    _require_fields(payload, ("seller_id",))
    seller_id = payload["seller_id"]
    session_id = request.get("session_id")
    _require_buyer_session(dbs, session_id)

    customer_db = _get_db(dbs, "customer")
    counts = repo.seller_feedback_counts(customer_db, seller_id)
    return {"feedback": counts}


def handle_get_buyer_purchases(request: Dict[str, Any], dbs: Dict[str, Database_Connection]) -> Dict[str, Any]:
    session_id = request.get("session_id")
    buyer_id = _require_buyer_session(dbs, session_id)
    product_db = _get_db(dbs, "product")
    rows = repo.buyer_purchases(product_db, buyer_id)
    purchases = [
        {"item_id": r[0], "quantity": r[1], "purchased_at": r[2].isoformat() if r[2] else None}
        for r in rows
    ]
    return {"items": purchases}


def handle_make_purchase(request: Dict[str, Any], dbs: Dict[str, Database_Connection]) -> Dict[str, Any]:
    payload = request.get("payload", {})
    _require_fields(payload, ("name", "card_number", "expiration_date", "security_code"))
    session_id = request.get("session_id")
    buyer_id = _require_buyer_session(dbs, session_id)

    product_db = _get_db(dbs, "product")

    # 1) Load saved cart (shared across sessions)
    cart_rows = repo.list_saved_cart(product_db, buyer_id)
    if not cart_rows:
        raise ValueError("CART_NOT_SAVED")

    # 2) Check stock
    cart_items = []
    for item_id, qty in cart_rows:
        stock = repo.get_item_stock(product_db, item_id)
        if stock is None or stock < qty:
            raise ValueError(f"ITEM_OUT_OF_STOCK:{item_id}")
        cart_items.append((item_id, qty))

    # 3) Call SOAP financial service
    try:
        soap_client = SoapClient(FINANCIAL_SERVICE_WSDL)
        success = soap_client.service.AuthorizePayment(
            username=payload["name"],
            card_number=payload["card_number"],
            expiration_date=payload["expiration_date"],
            security_code=payload["security_code"],
        )
    except Exception as e:
        raise ValueError(f"PAYMENT_SERVICE_UNAVAILABLE:{e}")

    if not success:
        raise ValueError("PAYMENT_DECLINED")

    # 4) Finalize: deduct stock, create purchases
    for item_id, qty in cart_items:
        repo.update_item_quantity(product_db, item_id, -qty)
        repo.create_purchase(product_db, buyer_id, item_id, qty)

    # 5) Clear saved cart after purchase
    product_db.execute(
        "DELETE FROM cart_items WHERE buyer_id = %s AND is_saved = TRUE",
        (buyer_id,),
        fetch=False,
    )

    return {"status": "success"}


# ---------- Handler map ----------

HANDLERS = {
    "CreateAccount": handle_create_account,
    "Login": handle_login,
    "Logout": handle_logout,
    "SearchItemsForSale": handle_search_items_for_sale,
    "GetItem": handle_get_item,
    "AddItemToCart": handle_add_item_to_cart,
    "RemoveItemFromCart": handle_remove_item_from_cart,
    "SaveCart": handle_save_cart,
    "ClearCart": handle_clear_cart,
    "DisplayCart": handle_display_cart,
    "ProvideFeedback": handle_provide_feedback,
    "GetSellerRating": handle_get_seller_rating,
    "GetBuyerPurchases": handle_get_buyer_purchases,
    "MakePurchase": handle_make_purchase,
}
