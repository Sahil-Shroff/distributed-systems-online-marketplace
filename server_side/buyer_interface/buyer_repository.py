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
        """
        UPDATE sessions 
        SET last_access_timestamp = NOW() 
        WHERE session_id = %s 
          AND last_access_timestamp > NOW() - INTERVAL '5 minutes'
        RETURNING user_id, role
        """,
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
        f"SELECT item_id, item_name, category, keywords, condition_is_new, sale_price, quantity, seller_id FROM items {where}",
        tuple(params),
        fetch=True,
    ) or []


def get_item(product_db: Database_Connection, item_id: Any):
    row = product_db.execute(
        "SELECT item_id, item_name, category, keywords, condition_is_new, sale_price, quantity, seller_id FROM items WHERE item_id = %s",
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

def add_item_to_cart(product_db: Database_Connection, buyer_id: int, session_id: str, item_id: Any, qty: int):
    product_db.execute(
        """
        INSERT INTO cart_items (buyer_id, session_id, item_id, quantity, is_saved)
        VALUES (%s, %s, %s, %s, FALSE)
        ON CONFLICT (buyer_id, session_id, item_id, is_saved) DO UPDATE
        SET quantity = cart_items.quantity + EXCLUDED.quantity
        """,
        (buyer_id, session_id, item_id, qty),
        fetch=False,
    )


def get_cart_item_quantity(product_db: Database_Connection, buyer_id: int, session_id: str, item_id: Any) -> Optional[int]:
    row = product_db.execute(
        "SELECT quantity FROM cart_items WHERE buyer_id = %s AND session_id = %s AND item_id = %s AND is_saved = FALSE",
        (buyer_id, session_id, item_id),
        fetch=True,
    )
    return row[0][0] if row else None


def update_cart_item(product_db: Database_Connection, buyer_id: int, session_id: str, item_id: Any, new_qty: int):
    if new_qty <= 0:
        product_db.execute(
            "DELETE FROM cart_items WHERE buyer_id = %s AND session_id = %s AND item_id = %s AND is_saved = FALSE",
            (buyer_id, session_id, item_id),
            fetch=False,
        )
    else:
        product_db.execute(
            "UPDATE cart_items SET quantity = %s WHERE buyer_id = %s AND session_id = %s AND item_id = %s AND is_saved = FALSE",
            (new_qty, buyer_id, session_id, item_id),
            fetch=False,
        )


def save_cart(product_db: Database_Connection, buyer_id: int, session_id: str):
    # Move session cart (is_saved=FALSE) into saved bucket (session_id='', is_saved=TRUE)
    product_db.execute(
        """
        INSERT INTO cart_items (buyer_id, session_id, item_id, quantity, is_saved)
        SELECT buyer_id, '', item_id, quantity, TRUE
        FROM cart_items
        WHERE buyer_id = %s AND session_id = %s AND is_saved = FALSE
        ON CONFLICT (buyer_id, session_id, item_id, is_saved)
        DO UPDATE SET quantity = cart_items.quantity + EXCLUDED.quantity
        """,
        (buyer_id, session_id),
        fetch=False,
    )
    # Clear the session cart
    product_db.execute(
        "DELETE FROM cart_items WHERE buyer_id = %s AND session_id = %s AND is_saved = FALSE",
        (buyer_id, session_id),
        fetch=False,
    )


def delete_unsaved_cart(product_db: Database_Connection, buyer_id: int, session_id: str):
    product_db.execute(
        "DELETE FROM cart_items WHERE buyer_id = %s AND session_id = %s AND is_saved = FALSE",
        (buyer_id, session_id),
        fetch=False,
    )


def clear_cart(product_db: Database_Connection, buyer_id: int, session_id: str):
    product_db.execute(
        "DELETE FROM cart_items WHERE buyer_id = %s AND session_id = %s AND is_saved = FALSE",
        (buyer_id, session_id),
        fetch=False,
    )


def list_cart(product_db: Database_Connection, buyer_id: int, session_id: str):
    return product_db.execute(
        "SELECT item_id, quantity FROM cart_items WHERE buyer_id = %s AND session_id = %s AND is_saved = FALSE",
        (buyer_id, session_id),
        fetch=True,
    ) or []


# ---------- Feedback / Rating ----------

def provide_feedback(product_db: Database_Connection, customer_db: Database_Connection, item_id: Any, buyer_id: int, is_positive: bool):
    # Find seller_id for the item
    row = product_db.execute(
        "SELECT seller_id FROM items WHERE item_id = %s",
        (item_id,),
        fetch=True,
    )
    if not row:
        raise ValueError("item not found")
    seller_id = row[0][0]

    # Update aggregated seller_feedback array: [positive_count, negative_count]
    customer_db.execute(
        """
        UPDATE sellers
        SET seller_feedback = ARRAY[
            COALESCE(seller_feedback[1], 0) + CASE WHEN %s THEN 1 ELSE 0 END,
            COALESCE(seller_feedback[2], 0) + CASE WHEN %s THEN 0 ELSE 1 END
        ]
        WHERE seller_id = %s
        """,
        (is_positive, is_positive, seller_id),
        fetch=False,
    )


def seller_feedback_counts(customer_db: Database_Connection, seller_id: int):
    row = customer_db.execute(
        "SELECT seller_feedback FROM sellers WHERE seller_id = %s",
        (seller_id,),
        fetch=True,
    )
    if not row:
        return None
    feedback = row[0][0]  # expected int[]
    if feedback is None or len(feedback) < 2:
        return None
    pos, neg = feedback[0], feedback[1]
    return {"pos": pos, "neg": neg}


# ---------- Purchases ----------

def buyer_purchases(product_db: Database_Connection, buyer_id: int):
    return product_db.execute(
        "SELECT item_id, quantity, purchased_at FROM purchases WHERE buyer_id = %s ORDER BY purchased_at DESC",
        (buyer_id,),
        fetch=True,
    ) or []
