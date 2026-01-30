import os
from typing import Any, Dict, Iterable, Tuple

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


def handle_create_account(request: Dict[str, Any], dbs: Dict[str, Database_Connection]) -> Dict[str, Any]:
    payload = request.get("payload", {})
    _require_fields(payload, ("username", "password"))
    username = payload["username"]
    password = payload["password"]

    customer_db = _get_db(dbs, "customer")

    rows = customer_db.execute(
        "INSERT INTO sellers (username, password) VALUES (%s, %s) RETURNING seller_id",
        (username, password),
        fetch=True,
    )

    seller_id = rows[0][0] if rows else None

    return {"seller_id": seller_id}

def handle_login(request: Dict[str, Any], dbs: Dict[str, Database_Connection]) -> Dict[str, Any]:
    payload = request.get("payload", {})
    _require_fields(payload, ("username", "password"))
    username = payload["username"]
    password = payload["password"]

    customer_db = _get_db(dbs, "customer")

    rows = customer_db.execute(
        "SELECT seller_id FROM sellers WHERE username = %s AND password = %s",
        (username, password),
        fetch=True,
    )

    if not rows:
        raise ValueError("invalid username or password")
    
    seller_id = rows[0][0]

    customer_db.execute(
        "INSERT INTO sessions (role, user_id, last_access_timestamp) VALUES (%s, %s, NOW())",
        ("seller", seller_id),
        fetch=False,
    )

    rows = customer_db.execute(
        "SELECT session_id FROM sessions WHERE role = %s AND user_id = %s ORDER BY last_access_timestamp DESC LIMIT 1",
        ("seller", seller_id),
        fetch=True,
    )

    session_id = rows[0][0] if rows else None

    return {"session_id": session_id, "seller_id": seller_id}


def handle_logout(request: Dict[str, Any], dbs: Dict[str, Database_Connection]) -> Dict[str, Any]:
    session_id = request.get("session_id")
    if not session_id:
        raise ValueError("session_id required for logout")

    db = _get_db(dbs, "customer")

    rows = db.execute(
        "SELECT user_id, role FROM sessions WHERE session_id = %s",
        (session_id,),
        fetch=True,
    )
    if not rows:
        return {"status": "success"} # Session already deleted

    user_id, role = rows[0]
    if isinstance(role, memoryview):
        role = role.tobytes()
    if isinstance(role, bytes):
        role = role.decode("utf-8")
    if role != "seller":
        raise ValueError("invalid role for logout")

    _delete_sessions(db, session_id, user_id, role)
    return {"status": "success", "scope": LOGOUT_SCOPE}


def handle_get_seller_rating(request: Dict[str, Any], dbs: Dict[str, Database_Connection]) -> Dict[str, Any]:
    session_id = request.get("session_id")
    seller_id = _require_seller_session(dbs, session_id)

    customer_db = _get_db(dbs, "customer")
    rows = customer_db.execute(
        "SELECT seller_feedback FROM sellers WHERE seller_id = %s",
        (seller_id,),
        fetch=True,
    )
    rating = None
    if rows:
        feedback = rows[0][0]
        if feedback is not None and len(feedback) >= 2:
            pos, neg = feedback[0], feedback[1]
            total = pos + neg
            if total > 0:
                rating = pos / total

    return {"rating": rating}


def _require_seller_session(dbs: Dict[str, Database_Connection], session_id: str) -> int:
    if not session_id:
        raise ValueError("session_id required")
    customer_db = _get_db(dbs, "customer")
    rows = customer_db.execute(
        "SELECT user_id, role FROM sessions WHERE session_id = %s",
        (session_id,),
        fetch=True,
    )
    if not rows:
        raise ValueError("invalid session")
    user_id, role = rows[0]
    if isinstance(role, memoryview):
        role = role.tobytes()
    if isinstance(role, bytes):
        role = role.decode("utf-8")
    if role != "seller":
        raise ValueError("invalid role for this operation")
    return user_id


def handle_register_item_for_sale(request: Dict[str, Any], dbs: Dict[str, Database_Connection]) -> Dict[str, Any]:
    payload = request.get("payload", {})
    _require_fields(payload, ("item_name", "category", "price", "quantity"))
    item_name = payload["item_name"]
    category = payload["category"]
    keywords = payload.get("keywords", [])
    condition = (payload.get("condition") or "").lower()
    price = payload["price"]
    quantity = payload["quantity"]
    session_id = request.get("session_id")
    seller_id = _require_seller_session(dbs, session_id)

    if not isinstance(keywords, list):
        raise ValueError("keywords must be a list")

    product_db = _get_db(dbs, "product")

    condition_is_new = condition in ("new", "brand new", "mint")

    rows = product_db.execute(
        """
        INSERT INTO items (item_name, category, keywords, condition_is_new, sale_price, quantity, seller_id)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        RETURNING item_id
        """,
        (item_name, category, keywords, condition_is_new, price, quantity, seller_id),
        fetch=True,
    )

    item_id = rows[0][0] if rows else None
    return {"item_id": item_id}


def handle_change_item_price(request: Dict[str, Any], dbs: Dict[str, Database_Connection]) -> Dict[str, Any]:
    payload = request.get("payload", {})
    _require_fields(payload, ("item_id", "price"))
    item_id = payload["item_id"]
    new_price = payload["price"]
    session_id = request.get("session_id")

    seller_id = _require_seller_session(dbs, session_id)
    product_db = _get_db(dbs, "product")

    rows = product_db.execute(
        "UPDATE items SET sale_price = %s WHERE item_id = %s AND seller_id = %s RETURNING item_id",
        (new_price, item_id, seller_id),
        fetch=True,
    )
    if not rows:
        raise ValueError("item not found or not owned by seller")

    return {"status": "success"}


def handle_update_units_for_sale(request: Dict[str, Any], dbs: Dict[str, Database_Connection]) -> Dict[str, Any]:
    payload = request.get("payload", {})
    _require_fields(payload, ("item_id", "quantity"))
    item_id = payload["item_id"]
    delta = payload["quantity"]
    session_id = request.get("session_id")

    seller_id = _require_seller_session(dbs, session_id)
    product_db = _get_db(dbs, "product")

    rows = product_db.execute(
        "SELECT quantity FROM items WHERE item_id = %s AND seller_id = %s",
        (item_id, seller_id),
        fetch=True,
    )
    if not rows:
        raise ValueError("item not found or not owned by seller")

    current_qty = rows[0][0]
    # delta represents change (can be negative or positive)
    new_qty = current_qty + delta
    if new_qty < 0:
        raise ValueError("INSUFFICIENT_QUANTITY")

    product_db.execute(
        "UPDATE items SET quantity = %s WHERE item_id = %s AND seller_id = %s",
        (new_qty, item_id, seller_id),
        fetch=False,
    )

    return {"status": "success", "quantity": new_qty}


def handle_display_items_for_sale(request: Dict[str, Any], dbs: Dict[str, Database_Connection]) -> Dict[str, Any]:
    session_id = request.get("session_id")
    seller_id = _require_seller_session(dbs, session_id)

    product_db = _get_db(dbs, "product")

    rows = product_db.execute(
        "SELECT item_id, item_name, category, keywords, condition_is_new, sale_price, quantity FROM items WHERE seller_id = %s",
        (seller_id,),
        fetch=True,
    ) or []

    items = [
        {
            "item_id": r[0],
            "item_name": r[1],
            "category": r[2],
            "keywords": r[3],
            "condition_is_new": r[4],
            "price": float(r[5]) if r[5] is not None else None,
            "quantity": r[6],
        }
        for r in rows
    ]

    return {"items": items}


HANDLERS = {
    "CreateAccount": handle_create_account,
    "Login": handle_login,
    "Logout": handle_logout,
    "GetSellerRating": handle_get_seller_rating,
    "RegisterItemForSale": handle_register_item_for_sale,
    "ChangeItemPrice": handle_change_item_price,
    "UpdateUnitsForSale": handle_update_units_for_sale,
    "DisplayItemsForSale": handle_display_items_for_sale,
}
