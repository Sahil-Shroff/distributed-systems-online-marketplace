from typing import Any, Dict

from server_side.data_access_layer.db import Database_Connection


def handle_create_account(request: Dict[str, Any], dbs: Dict[str, Database_Connection]) -> Dict[str, Any]:
    payload = request.get("payload", {})
    username = payload.get("username")
    password = payload.get("password")

    if not username or not password:
        raise ValueError("username and password are required")

    customer_db = dbs.get("customer")
    if customer_db is None:
        raise RuntimeError("customer database connection is not configured")

    customer_db.execute(
        "INSERT INTO sellers (username, password) VALUES (%s, %s)",
        (username, password),
        fetch=False,
    )

    rows = customer_db.execute(
        "SELECT seller_id FROM sellers WHERE username = %s",
        (username,),
        fetch=True,
    )

    seller_id = rows[0][0] if rows else None

    return {"seller_id": seller_id}

def handle_login(request: Dict[str, Any], dbs: Dict[str, Database_Connection]) -> Dict[str, Any]:
    payload = request.get("payload", {})
    username = payload.get("username")
    password = payload.get("password")

    if not username or not password:
        raise ValueError("username and password are required")

    customer_db = dbs.get("customer")
    if customer_db is None:
        raise RuntimeError("customer database connection is not configured")
    
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
    # TODO: implement logout logic
    return {"status": "success", "note": "Logout not yet implemented"}


def handle_get_seller_rating(request: Dict[str, Any], dbs: Dict[str, Database_Connection]) -> Dict[str, Any]:
    # TODO: implement rating retrieval
    return {"status": "success", "note": "GetSellerRating not yet implemented"}


def handle_register_item_for_sale(request: Dict[str, Any], dbs: Dict[str, Database_Connection]) -> Dict[str, Any]:
    payload = request.get("payload", {})
    name = payload.get("item_name")
    category = payload.get("category")
    condition = payload.get("condition")
    price = payload.get("price")
    quantity = payload.get("quantity")
    keywords = payload.get("keywords", [])

    if not all([name, category, condition, price, quantity]):
        raise ValueError("Missing required item fields")

    seller_db = dbs.get("seller")
    if seller_db is None:
        raise RuntimeError("seller database connection is not configured")

    seller_db.execute(
        "INSERT INTO items (name, category, condition, price, quantity) VALUES (%s, %s, %s, %s, %s)",
        (name, category, condition, price, quantity),
        fetch=False,
    )

    rows = seller_db.execute(
        "SELECT item_id FROM items WHERE name = %s AND category = %s AND condition = %s AND price = %s AND quantity = %s",
        (name, category, condition, price, quantity),
        fetch=True,
    )

    item_id = rows[0][0] if rows else None

    return {"item_id": item_id}


def handle_change_item_price(request: Dict[str, Any], dbs: Dict[str, Database_Connection]) -> Dict[str, Any]:
    # TODO: implement price change
    return {"status": "success", "note": "ChangeItemPrice not yet implemented"}


def handle_update_units_for_sale(request: Dict[str, Any], dbs: Dict[str, Database_Connection]) -> Dict[str, Any]:
    # TODO: implement inventory update
    return {"status": "success", "note": "UpdateUnitsForSale not yet implemented"}


def handle_display_items_for_sale(request: Dict[str, Any], dbs: Dict[str, Database_Connection]) -> Dict[str, Any]:
    # TODO: implement items listing
    return {"status": "success", "note": "DisplayItemsForSale not yet implemented"}


# Mapping from API name to handler function
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
