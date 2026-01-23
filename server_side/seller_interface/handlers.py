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
    # TODO: implement login logic
    return {"status": "success", "note": "Login not yet implemented"}


def handle_logout(request: Dict[str, Any], dbs: Dict[str, Database_Connection]) -> Dict[str, Any]:
    # TODO: implement logout logic
    return {"status": "success", "note": "Logout not yet implemented"}


def handle_get_seller_rating(request: Dict[str, Any], dbs: Dict[str, Database_Connection]) -> Dict[str, Any]:
    # TODO: implement rating retrieval
    return {"status": "success", "note": "GetSellerRating not yet implemented"}


def handle_register_item_for_sale(request: Dict[str, Any], dbs: Dict[str, Database_Connection]) -> Dict[str, Any]:
    # TODO: implement item registration
    return {"status": "success", "note": "RegisterItemForSale not yet implemented"}


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
