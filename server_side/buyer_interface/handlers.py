import os
from typing import Any, Dict, Iterable, List

from server_side.data_access_layer.db import Database_Connection
from server_side.buyer_interface import buyer_repository as repo

# "single", "all" - determines whether logout invalidates only the current session or all sessions
LOGOUT_SCOPE = os.getenv("LOGOUT_SCOPE", "single").lower()


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
            "keywords": r[2],
            "condition_is_new": r[3],
            "price": float(r[4]) if r[4] is not None else None,
            "quantity": r[5],
            "seller_id": r[6],
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
        "keywords": row[2],
        "condition_is_new": row[3],
        "price": float(row[4]) if row[4] is not None else None,
        "quantity": row[5],
        "seller_id": row[6],
    }


# ---------- Cart operations ----------

def handle_add_item_to_cart(request: Dict[str, Any], dbs: Dict[str, Database_Connection]) -> Dict[str, Any]:
    payload = request.get("payload", {})
    _require_fields(payload, ("item_id", "quantity"))
    item_id = payload["item_id"]
    qty = payload["quantity"]
    session_id = request.get("session_id")
    buyer_id = _require_buyer_session(dbs, session_id)

    product_db = _get_db(dbs, "product")
    available = repo.get_item_stock(product_db, item_id)
    if available is None:
        raise ValueError("item not found")
    if qty > available:
        raise ValueError("ITEM_OUT_OF_STOCK")

    customer_db = _get_db(dbs, "customer")
    repo.add_item_to_cart(customer_db, buyer_id, item_id, qty)
    return {"status": "success"}


def handle_remove_item_from_cart(request: Dict[str, Any], dbs: Dict[str, Database_Connection]) -> Dict[str, Any]:
    payload = request.get("payload", {})
    _require_fields(payload, ("item_id", "quantity"))
    item_id = payload["item_id"]
    qty = payload["quantity"]
    session_id = request.get("session_id")
    buyer_id = _require_buyer_session(dbs, session_id)

    customer_db = _get_db(dbs, "customer")
    current = repo.get_cart_item_quantity(customer_db, buyer_id, item_id)
    if current is None:
        raise ValueError("item not in cart")
    new_qty = current - qty
    repo.update_cart_item(customer_db, buyer_id, item_id, new_qty)
    return {"status": "success", "quantity": max(new_qty, 0)}


def handle_save_cart(request: Dict[str, Any], dbs: Dict[str, Database_Connection]) -> Dict[str, Any]:
    # If cart_items persists in DB, this is effectively a no-op.
    session_id = request.get("session_id")
    _require_buyer_session(dbs, session_id)
    return {"status": "success"}


def handle_clear_cart(request: Dict[str, Any], dbs: Dict[str, Database_Connection]) -> Dict[str, Any]:
    session_id = request.get("session_id")
    buyer_id = _require_buyer_session(dbs, session_id)
    customer_db = _get_db(dbs, "customer")
    repo.clear_cart(customer_db, buyer_id)
    return {"status": "success"}


def handle_display_cart(request: Dict[str, Any], dbs: Dict[str, Database_Connection]) -> Dict[str, Any]:
    session_id = request.get("session_id")
    buyer_id = _require_buyer_session(dbs, session_id)
    customer_db = _get_db(dbs, "customer")
    rows = repo.list_cart(customer_db, buyer_id)
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
    repo.provide_feedback(product_db, item_id, buyer_id, is_positive)
    return {"status": "success"}


def handle_get_seller_rating(request: Dict[str, Any], dbs: Dict[str, Database_Connection]) -> Dict[str, Any]:
    payload = request.get("payload", {})
    _require_fields(payload, ("seller_id",))
    seller_id = payload["seller_id"]
    session_id = request.get("session_id")
    _require_buyer_session(dbs, session_id)

    product_db = _get_db(dbs, "product")
    rating = repo.seller_rating(product_db, seller_id)
    return {"rating": rating}


def handle_get_buyer_purchases(request: Dict[str, Any], dbs: Dict[str, Database_Connection]) -> Dict[str, Any]:
    session_id = request.get("session_id")
    buyer_id = _require_buyer_session(dbs, session_id)
    customer_db = _get_db(dbs, "customer")
    rows = repo.buyer_purchases(customer_db, buyer_id)
    purchases = [
        {"item_id": r[0], "quantity": r[1], "purchased_at": r[2].isoformat() if r[2] else None}
        for r in rows
    ]
    return {"items": purchases}


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
}
