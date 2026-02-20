#!/usr/bin/env bash
set -euo pipefail

PROJECT="$(gcloud config get-value project)"
REGION="us-central1"
INSTANCE="marketplace-sql"
TIER="db-f1-micro"            # cheapest; adjust if you need more CPU/RAM
PG_VERSION="POSTGRES_17"
ROOT_PW="${ROOT_PW:-password}"  # override with env var
DB_USER="postgres"

echo "Creating Cloud SQL instance '${INSTANCE}' in ${PROJECT}/${REGION}..."
gcloud sql instances create "${INSTANCE}" \
  --database-version="${PG_VERSION}" \
  --tier="${TIER}" \
  --region="${REGION}" \
  --root-password="${ROOT_PW}" \
  --storage-size=10 \
  --storage-auto-increase \
  --quiet

echo "Enabling public IP (simplest for a quick test)..."
gcloud sql instances patch "${INSTANCE}" --assign-ip --quiet

echo "Creating databases..."
for DB in customer-database product-database financial-database; do
  gcloud sql databases create "${DB}" --instance="${INSTANCE}" --quiet
done

# Fetch the public IP for psql connections
IP=$(gcloud sql instances describe "${INSTANCE}" --format="value(ipAddresses.ipAddress)")
echo "Instance IP: ${IP}"

# Apply schemas using psql (requires local psql; uses root user)
PSQL="psql \"host=${IP} user=${DB_USER} password=${ROOT_PW} sslmode=require\""

echo "Applying customer-database schema..."
$PSQL -d customer-database <<'SQL'
CREATE TABLE IF NOT EXISTS buyers (
  buyer_id SERIAL PRIMARY KEY,
  username VARCHAR(255) NOT NULL,
  password TEXT NOT NULL,
  items_purchased INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS sellers (
  seller_id SERIAL PRIMARY KEY,
  seller_feedback INTEGER[] DEFAULT '{0,0}',
  items_sold INTEGER DEFAULT 0,
  username VARCHAR(255) NOT NULL,
  password VARCHAR(255) NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
  session_id SERIAL PRIMARY KEY,
  role VARCHAR(16) NOT NULL CHECK (role IN ('seller','buyer')),
  user_id INTEGER NOT NULL,
  last_access_timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_sessions_user_role ON sessions(user_id, role);
SQL

echo "Applying product-database schema..."
$PSQL -d product-database <<'SQL'
CREATE TABLE IF NOT EXISTS items (
  item_id SERIAL PRIMARY KEY,
  item_name VARCHAR(255) NOT NULL,
  category INTEGER NOT NULL DEFAULT 0,
  keywords TEXT[] NULL,
  condition_is_new BOOLEAN DEFAULT TRUE,
  sale_price NUMERIC DEFAULT 0,
  quantity INTEGER DEFAULT 0,
  item_feedback INTEGER[] DEFAULT '{0,0}',
  seller_id INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS cart_items (
  cart_item_id SERIAL PRIMARY KEY,
  buyer_id INTEGER NOT NULL,
  session_id VARCHAR NOT NULL DEFAULT '',
  item_id INTEGER NOT NULL,
  quantity INTEGER NOT NULL,
  is_saved BOOLEAN NOT NULL DEFAULT FALSE,
  CONSTRAINT cart_items_buyer_session_item_saved_uniq UNIQUE (buyer_id, session_id, item_id, is_saved)
);
CREATE TABLE IF NOT EXISTS purchases (
  purchase_id SERIAL PRIMARY KEY,
  buyer_id INTEGER NOT NULL,
  item_id INTEGER NOT NULL,
  quantity INTEGER NOT NULL,
  purchased_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
SQL

echo "Applying financial-database schema..."
$PSQL -d financial-database <<'SQL'
CREATE TABLE IF NOT EXISTS transactions (
  id SERIAL PRIMARY KEY,
  username VARCHAR(128) NOT NULL,
  card_last4 VARCHAR(4) NOT NULL,
  expiration_date VARCHAR(10) NOT NULL,
  approved BOOLEAN NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
SQL

echo "Done. Connect with:"
echo "  psql \"host=${IP} user=${DB_USER} password=${ROOT_PW} dbname=customer-database sslmode=require\""
echo "  psql \"host=${IP} user=${DB_USER} password=${ROOT_PW} dbname=product-database sslmode=require\""
echo "  psql \"host=${IP} user=${DB_USER} password=${ROOT_PW} dbname=financial-database sslmode=require\""