CUSTOMER_SQLITE_DEFAULT_DB = "customer-database.sqlite"
PRODUCT_SQLITE_DEFAULT_DB = "product-database.sqlite"

PRODUCT_SQLITE_SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
  item_id INTEGER PRIMARY KEY AUTOINCREMENT,
  item_name TEXT NOT NULL,
  category INTEGER NOT NULL DEFAULT 0,
  keywords TEXT NOT NULL DEFAULT '[]',
  condition_is_new INTEGER NOT NULL DEFAULT 1,
  sale_price REAL NOT NULL DEFAULT 0,
  quantity INTEGER NOT NULL DEFAULT 0,
  item_feedback TEXT NOT NULL DEFAULT '[0, 0]',
  seller_id INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS cart_items (
  cart_item_id INTEGER PRIMARY KEY AUTOINCREMENT,
  buyer_id INTEGER NOT NULL,
  session_id TEXT NOT NULL DEFAULT '',
  item_id INTEGER NOT NULL,
  quantity INTEGER NOT NULL,
  is_saved INTEGER NOT NULL DEFAULT 0,
  UNIQUE (buyer_id, session_id, item_id, is_saved)
);

CREATE TABLE IF NOT EXISTS purchases (
  purchase_id INTEGER PRIMARY KEY AUTOINCREMENT,
  buyer_id INTEGER NOT NULL,
  item_id INTEGER NOT NULL,
  quantity INTEGER NOT NULL,
  purchased_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""
