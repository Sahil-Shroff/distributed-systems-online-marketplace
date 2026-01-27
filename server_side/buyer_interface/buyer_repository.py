from typing import Any, Iterable, List, Optional, Tuple

from server_side.data_access_layer.db import Database_Connection


# ---------- Account / Session ----------

def create_buyer(customer_db: Database_Connection, username: str, password: str) -> Optional[int]:
    row = customer_db.execute(
        "INSERT INTO buyers (username, password, items_purchased) VALUES (%s, %s, 0) RETURNING buyer_id",
        (username, password),
        fetch=True,
    )
    return row[0][0] if row else None


def authenticate_buyer(customer_db: Database_Connection, username: str, password: str) -> Optional[int]:
    row = customer_db.execute(
        "SELECT buyer_id FROM buyers WHERE username = %s AND password = %s",
        (username, password),
        fetch=True,
    )
    return row[0][0] if row else None


def create_session(customer_db: Database_Connection, buyer_id: int) -> Optional[str]:
    customer_db.execute(
        "INSERT INTO sessions (role, user_id, last_access_timestamp) VALUES (%s, %s, NOW())",
        ("buyer", buyer_id),
        fetch=False,
    )
    row = customer_db.execute(
        "SELECT session_id FROM sessions WHERE role = %s AND user_id = %s ORDER BY last_access_timestamp DESC LIMIT 1",
        ("buyer", buyer_id),
        fetch=True,
    )
    return row[0][0] if row else None


def fetch_session(customer_db: Database_Connection, session_id: str) -> Optional[Tuple[int, str]]:
    row = customer_db.execute(
        "SELECT user_id, role FROM sessions WHERE session_id = %s",
        (session_id,),
        fetch=True,
    )
    return row[0] if row else None


def delete_sessions(customer_db: Database_Connection, session_id: str, user_id: int, role: str, scope: str):
    if scope == "all":
        customer_db.execute(
            "DELETE FROM sessions WHERE user_id = %s AND role = %s",
            (user_id, role),
            fetch=False,
        )
    else:
        customer_db.execute(
            "DELETE FROM sessions WHERE session_id = %s",
            (session_id,),
            fetch=False,
        )


# ---------- Items ----------

def search_items(product_db: Database_Connection, category: Any = None, keywords: List[str] | None = None):
    params: List[Any] = []
    clauses: List[str] = []
    if category is not None:
        clauses.append("category = %s")
        params.append(category)
    if keywords:
        clauses.append("%s = ANY(keywords)")
        params.append(keywords[0])
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    return product_db.execute(
        f"SELECT item_id, item_name, keywords, condition_is_new, sale_price, quantity, seller_id FROM items {where}",
        tuple(params),
        fetch=True,
    ) or []


def get_item(product_db: Database_Connection, item_id: Any):
    row = product_db.execute(
        "SELECT item_id, item_name, keywords, condition_is_new, sale_price, quantity, seller_id FROM items WHERE item_id = %s",
        (item_id,),
        fetch=True,
    )
    return row[0] if row else None


def get_item_stock(product_db: Database_Connection, item_id: Any) -> Optional[int]:
    row = product_db.execute(
        "SELECT quantity FROM items WHERE item_id = %s",
        (item_id,),
        fetch=True,
    )
    return row[0][0] if row else None


# ---------- Cart ----------

def add_item_to_cart(customer_db: Database_Connection, buyer_id: int, item_id: Any, qty: int):
    customer_db.execute(
        """
        INSERT INTO cart_items (buyer_id, item_id, quantity)
        VALUES (%s, %s, %s)
        ON CONFLICT (buyer_id, item_id) DO UPDATE SET quantity = cart_items.quantity + EXCLUDED.quantity
        """,
        (buyer_id, item_id, qty),
        fetch=False,
    )


def get_cart_item_quantity(customer_db: Database_Connection, buyer_id: int, item_id: Any) -> Optional[int]:
    row = customer_db.execute(
        "SELECT quantity FROM cart_items WHERE buyer_id = %s AND item_id = %s",
        (buyer_id, item_id),
        fetch=True,
    )
    return row[0][0] if row else None


def update_cart_item(customer_db: Database_Connection, buyer_id: int, item_id: Any, new_qty: int):
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


def clear_cart(customer_db: Database_Connection, buyer_id: int):
    customer_db.execute(
        "DELETE FROM cart_items WHERE buyer_id = %s",
        (buyer_id,),
        fetch=False,
    )


def list_cart(customer_db: Database_Connection, buyer_id: int):
    return customer_db.execute(
        "SELECT item_id, quantity FROM cart_items WHERE buyer_id = %s",
        (buyer_id,),
        fetch=True,
    ) or []


# ---------- Feedback / Rating ----------

def provide_feedback(product_db: Database_Connection, item_id: Any, buyer_id: int, is_positive: bool):
    product_db.execute(
        "INSERT INTO item_feedback (item_id, buyer_id, is_positive) VALUES (%s, %s, %s)",
        (item_id, buyer_id, is_positive),
        fetch=False,
    )


def seller_rating(product_db: Database_Connection, seller_id: int):
    row = product_db.execute(
        "SELECT AVG(CASE WHEN is_positive THEN 1 ELSE 0 END) FROM item_feedback f JOIN items i ON f.item_id = i.item_id WHERE i.seller_id = %s",
        (seller_id,),
        fetch=True,
    )
    return float(row[0][0]) if row and row[0][0] is not None else None


# ---------- Purchases ----------

def buyer_purchases(customer_db: Database_Connection, buyer_id: int):
    return customer_db.execute(
        "SELECT item_id, quantity, purchased_at FROM purchases WHERE buyer_id = %s ORDER BY purchased_at DESC",
        (buyer_id,),
        fetch=True,
    ) or []
