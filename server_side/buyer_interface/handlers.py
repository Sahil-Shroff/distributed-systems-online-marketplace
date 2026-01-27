import os
from typing import Any, Dict, Iterable, Tuple, List

from server_side.data_access_layer.db import Database_Connection

# "single", "all" - determines whether logout invalidates only the current session or all sessions
LOGOUT_SCOPE = os.getenv("LOGOUT_SCOPE", "single").lower()

def _get_db(dbs: Dict[str, Database_Connection], key: str) -> Database_Connection:
    db = dbs.get(key)
    if db is None:
        raise RuntimeError(f"{key} database connection is not configured")
    return db

def _require_fields(payload: Dict[str, Any], required: Iterable[str]):
    missing = [f for f in required if payload.get(f) is None]
    if missing:
        raise ValueError(f"Missing required fields: {', '.join(missing)}")

def _fetch_one(db: Database_Connection, query: str, params: Tuple[Any, ...]):
    rows = db.execute(query, params, fetch=True)
    return rows[0] if rows else None

def _delete_sessions(db: Database_Connection, session_id: str, user_id: int, role: str):
    if LOGOUT_SCOPE == "all":
        db.execute(
            "DELETE FROM sessions WHERE user_id = %s AND role = %s",
            (user_id, role),
            fetch=False,
        )
    else:  # default to single-session logout
        db.execute(
            "DELETE FROM sessions WHERE session_id = %s",
            (session_id,),
            fetch=False,
        )

def _require_buyer_session(dbs: Dict[str, Database_Connection], session_id: str) -> int:
    if not session_id:
        raise ValueError("session_id required")
    customer_db = _get_db(dbs, "customer")
    row = _fetch_one(
        customer_db,
        "SELECT user_id, role FROM sessions WHERE session_id = %s",
        (session_id,),
    )
    if not row:
        raise ValueError("invalid session")
    user_id, role = row
    if role != "buyer":
        raise ValueError("invalid role for this operation")
    return user_id

def handle_create_account(request: Dict[str, Any], dbs: Dict[str, Database_Connection]) -> Dict[str, Any]:
    payload = request.get("payload", {})
    _require_fields(payload, ("username", "password"))
    username = payload["username"]
    password = payload["password"]

    customer_db = _get_db(dbs, "customer")

    row = _fetch_one(
        customer_db,
        "INSERT INTO buyers (username, password, items_purchased) VALUES (%s, %s, 0) RETURNING buyer_id",
        (username, password),
    )
    buyer_id = row[0] if row else None
    return {"buyer_id": buyer_id}


def handle_login(request: Dict[str, Any], dbs: Dict[str, Database_Connection]) -> Dict[str, Any]:
    payload = request.get("payload", {})
    _require_fields(payload, ("username", "password"))
    username = payload["username"]
    password = payload["password"]

    customer_db = _get_db(dbs, "customer")

    row = _fetch_one(
        customer_db,
        "SELECT buyer_id FROM buyers WHERE username = %s AND password = %s",
        (username, password),
    )
    if not row:
        raise ValueError("invalid username or password")
    buyer_id = row[0]

    customer_db.execute(
        "INSERT INTO sessions (role, user_id, last_access_timestamp) VALUES (%s, %s, NOW())",
        ("buyer", buyer_id),
        fetch=False,
    )
    session_row = _fetch_one(
        customer_db,
        "SELECT session_id FROM sessions WHERE role = %s AND user_id = %s ORDER BY last_access_timestamp DESC LIMIT 1",
        ("buyer", buyer_id),
    )
    session_id = session_row[0] if session_row else None
    return {"session_id": session_id, "buyer_id": buyer_id}


def handle_logout(request: Dict[str, Any], dbs: Dict[str, Database_Connection]) -> Dict[str, Any]:
    session_id = request.get("session_id")
    if not session_id:
        raise ValueError("session_id required for logout")

    customer_db = _get_db(dbs, "customer")
    row = _fetch_one(
        customer_db,
        "SELECT user_id, role FROM sessions WHERE session_id = %s",
        (session_id,),
    )
    if not row:
        return {"status": "success"}  # idempotent
    user_id, role = row
    if role != "buyer":
        raise ValueError("invalid role for logout")

    _delete_sessions(customer_db, session_id, user_id, role)
    return {"status": "success", "scope": LOGOUT_SCOPE}

def handle_search_items_for_sale(request: Dict[str, Any], dbs: Dict[str, Database_Connection]) -> Dict[str, Any]:
    payload = request.get("payload", {})
    category = payload.get("category")
    keywords: List[str] = payload.get("keywords", [])
    session_id = request.get("session_id")
    _require_buyer_session(dbs, session_id)

    product_db = _get_db(dbs, "product")
    params: List[Any] = []
    clauses: List[str] = []
    if category is not None:
        clauses.append("category = %s")
        params.append(category)
    if keywords:
        # simple contains ANY match
        clauses.append("%s = ANY(keywords)")
        params.append(keywords[0])
        # For multiple keywords, you could expand; here we just use the first for simplicity.
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = product_db.execute(
        f"SELECT item_id, item_name, keywords, condition_is_new, sale_price, quantity, seller_id FROM items {where}",
        tuple(params),
        fetch=True,
    ) or []
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
    row = _fetch_one(
        product_db,
        "SELECT item_id, item_name, keywords, condition_is_new, sale_price, quantity, seller_id FROM items WHERE item_id = %s",
        (item_id,),
    )
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

def handle_add_item_to_cart(request: Dict[str, Any], dbs: Dict[str, Database_Connection]) -> Dict[str, Any]:
    payload = request.get("payload", {})
    _require_fields(payload, ("item_id", "quantity"))
    item_id = payload["item_id"]
    qty = payload["quantity"]
    session_id = request.get("session_id")
    buyer_id = _require_buyer_session(dbs, session_id)

    product_db = _get_db(dbs, "product")
    row = _fetch_one(
        product_db,
        "SELECT quantity FROM items WHERE item_id = %s",
        (item_id,),
    )
    if not row:
        raise ValueError("item not found")
    available = row[0]
    if qty > available:
        raise ValueError("ITEM_OUT_OF_STOCK")

    customer_db = _get_db(dbs, "customer")
    # Upsert into cart_items (assumes table: cart_items(buyer_id,item_id,quantity))
    customer_db.execute(
        """
        INSERT INTO cart_items (buyer_id, item_id, quantity)
        VALUES (%s, %s, %s)
        ON CONFLICT (buyer_id, item_id) DO UPDATE SET quantity = cart_items.quantity + EXCLUDED.quantity
        """,
        (buyer_id, item_id, qty),
        fetch=False,
    )
    return {"status": "success"}


def handle_remove_item_from_cart(request: Dict[str, Any], dbs: Dict[str, Database_Connection]) -> Dict[str, Any]:
    payload = request.get("payload", {})
    _require_fields(payload, ("item_id", "quantity"))
    item_id = payload["item_id"]
    qty = payload["quantity"]
    session_id = request.get("session_id")
    buyer_id = _require_buyer_session(dbs, session_id)

    customer_db = _get_db(dbs, "customer")
    row = _fetch_one(
        customer_db,
        "SELECT quantity FROM cart_items WHERE buyer_id = %s AND item_id = %s",
        (buyer_id, item_id),
    )
    if not row:
        raise ValueError("item not in cart")
    current = row[0]
    new_qty = current - qty
    if new_qty <= 0:
        customer_db.execute(
            "DELETE FROM cart_items WHERE buyer_id = %s AND item_id = %s",
            (buyer_id, item_id),
            fetch=False,
        )
    else:
        customer_db.execute(
            "UPDATE cart_items SET quantity = %s WHERE buyer_id = %s AND item_id = %s",
            (new_qty, buyer_id, item_id),
            fetch=False,
        )
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
    customer_db.execute(
        "DELETE FROM cart_items WHERE buyer_id = %s",
        (buyer_id,),
        fetch=False,
    )
    return {"status": "success"}


def handle_display_cart(request: Dict[str, Any], dbs: Dict[str, Database_Connection]) -> Dict[str, Any]:
    session_id = request.get("session_id")
    buyer_id = _require_buyer_session(dbs, session_id)
    customer_db = _get_db(dbs, "customer")
    rows = customer_db.execute(
        "SELECT item_id, quantity FROM cart_items WHERE buyer_id = %s",
        (buyer_id,),
        fetch=True,
    ) or []
    items = [{"item_id": r[0], "quantity": r[1]} for r in rows]
    return {"cart": items}

def handle_provide_feedback(request: Dict[str, Any], dbs: Dict[str, Database_Connection]) -> Dict[str, Any]:
    payload = request.get("payload", {})
    # client sends thumbs_up; accept either
    if "thumbs_up" in payload:
        payload["is_positive"] = payload["thumbs_up"]
    _require_fields(payload, ("item_id", "is_positive"))
    item_id = payload["item_id"]
    is_positive = bool(payload["is_positive"])
    session_id = request.get("session_id")
    buyer_id = _require_buyer_session(dbs, session_id)

    product_db = _get_db(dbs, "product")
    product_db.execute(
        "INSERT INTO item_feedback (item_id, buyer_id, is_positive) VALUES (%s, %s, %s)",
        (item_id, buyer_id, is_positive),
        fetch=False,
    )
    return {"status": "success"}


def handle_get_seller_rating(request: Dict[str, Any], dbs: Dict[str, Database_Connection]) -> Dict[str, Any]:
    payload = request.get("payload", {})
    _require_fields(payload, ("seller_id",))
    seller_id = payload["seller_id"]
    session_id = request.get("session_id")
    _require_buyer_session(dbs, session_id)

    product_db = _get_db(dbs, "product")
    row = _fetch_one(
        product_db,
        "SELECT AVG(CASE WHEN is_positive THEN 1 ELSE 0 END) FROM item_feedback f JOIN items i ON f.item_id = i.item_id WHERE i.seller_id = %s",
        (seller_id,),
    )
    rating = float(row[0]) if row and row[0] is not None else None
    return {"rating": rating}


def handle_get_buyer_purchases(request: Dict[str, Any], dbs: Dict[str, Database_Connection]) -> Dict[str, Any]:
    session_id = request.get("session_id")
    buyer_id = _require_buyer_session(dbs, session_id)
    customer_db = _get_db(dbs, "customer")
    rows = customer_db.execute(
        "SELECT item_id, quantity, purchased_at FROM purchases WHERE buyer_id = %s ORDER BY purchased_at DESC",
        (buyer_id,),
        fetch=True,
    ) or []
    purchases = [
        {"item_id": r[0], "quantity": r[1], "purchased_at": r[2].isoformat() if r[2] else None}
        for r in rows
    ]
    return {"items": purchases}

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
