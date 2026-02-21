@echo off
setlocal enabledelayedexpansion

rem Windows helper to mirror create_dbs.sh using gcloud + psql

rem Defaults (override by setting env vars before running; PROJECT can be overridden without changing gcloud default)
if "%REGION%"=="" set "REGION=us-central1"
if "%INSTANCE%"=="" set "INSTANCE=marketplace-sql"
rem Defaults – can be overridden via env vars before calling
if "%TIER%"=="" set "TIER=db-f1-micro"
if "%PG_VERSION%"=="" set "PG_VERSION=POSTGRES_17"
if "%ROOT_PW%"=="" set "ROOT_PW=password"
if "%DB_USER%"=="" set "DB_USER=postgres"
if "%PROJECT%"=="" for /f "tokens=*" %%i in ('gcloud config get-value project') do set "PROJECT=%%i"
if "%EDITION%"=="" set "EDITION=ENTERPRISE"

@REM if "%CREATE_INSTANCE%"=="" set "CREATE_INSTANCE=1"

@REM if "%CREATE_INSTANCE%"=="1" (
@REM   echo Creating Cloud SQL instance "%INSTANCE%" in %PROJECT%/%REGION%...
@REM   gcloud sql instances create "%INSTANCE%" ^
@REM     --project="%PROJECT%" ^
@REM     --database-version=%PG_VERSION% ^
@REM     --edition=%EDITION% ^
@REM     --tier=%TIER% ^
@REM     --region=%REGION% ^
@REM     --root-password="%ROOT_PW%" ^
@REM     --storage-size=10 ^
@REM     --storage-auto-increase ^
@REM     --quiet
@REM   if errorlevel 1 goto :fail

@REM   echo Enabling public IP...
@REM   gcloud sql instances patch "%INSTANCE%" --project="%PROJECT%" --assign-ip --quiet
@REM   if errorlevel 1 goto :fail
@REM ) else (
@REM   echo Skipping instance creation (CREATE_INSTANCE=0) using existing "%INSTANCE%".
@REM )

echo Creating databases...
for %%D in (customer-database product-database financial-database) do (
  gcloud sql databases create "%%D" --instance="%INSTANCE%" --project="%PROJECT%" --quiet
  if errorlevel 1 goto :fail
)

for /f "tokens=*" %%i in ('gcloud sql instances describe "%INSTANCE%" --project="%PROJECT%" --format^="value(ipAddresses.ipAddress)"') do set "IP=%%i"
echo Instance IP: %IP%

set "PSQL=psql \"host=%IP% user=%DB_USER% password=%ROOT_PW% sslmode=require\""

echo Applying customer-database schema...
call %PSQL% -d customer-database -c "CREATE TABLE IF NOT EXISTS buyers (buyer_id SERIAL PRIMARY KEY, username VARCHAR(255) NOT NULL, password TEXT NOT NULL, items_purchased INTEGER NOT NULL DEFAULT 0); CREATE TABLE IF NOT EXISTS sellers (seller_id SERIAL PRIMARY KEY, seller_feedback INTEGER[] DEFAULT '{0,0}', items_sold INTEGER DEFAULT 0, username VARCHAR(255) NOT NULL, password VARCHAR(255) NOT NULL); CREATE TABLE IF NOT EXISTS sessions (session_id SERIAL PRIMARY KEY, role VARCHAR(16) NOT NULL CHECK (role IN ('seller','buyer')), user_id INTEGER NOT NULL, last_access_timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW()); CREATE INDEX IF NOT EXISTS idx_sessions_user_role ON sessions(user_id, role);" || goto :fail

echo Applying product-database schema...
call %PSQL% -d product-database -c "CREATE TABLE IF NOT EXISTS items (item_id SERIAL PRIMARY KEY, item_name VARCHAR(255) NOT NULL, category INTEGER NOT NULL DEFAULT 0, keywords TEXT[] NULL, condition_is_new BOOLEAN DEFAULT TRUE, sale_price NUMERIC DEFAULT 0, quantity INTEGER DEFAULT 0, item_feedback INTEGER[] DEFAULT '{0,0}', seller_id INTEGER NOT NULL); CREATE TABLE IF NOT EXISTS cart_items (cart_item_id SERIAL PRIMARY KEY, buyer_id INTEGER NOT NULL, session_id VARCHAR NOT NULL DEFAULT '', item_id INTEGER NOT NULL, quantity INTEGER NOT NULL, is_saved BOOLEAN NOT NULL DEFAULT FALSE, CONSTRAINT cart_items_buyer_session_item_saved_uniq UNIQUE (buyer_id, session_id, item_id, is_saved)); CREATE TABLE IF NOT EXISTS purchases (purchase_id SERIAL PRIMARY KEY, buyer_id INTEGER NOT NULL, item_id INTEGER NOT NULL, quantity INTEGER NOT NULL, purchased_at TIMESTAMPTZ NOT NULL DEFAULT NOW());" || goto :fail

echo Applying financial-database schema...
call %PSQL% -d financial-database -c "CREATE TABLE IF NOT EXISTS transactions (id SERIAL PRIMARY KEY, username VARCHAR(128) NOT NULL, card_last4 VARCHAR(4) NOT NULL, expiration_date VARCHAR(10) NOT NULL, approved BOOLEAN NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW());" || goto :fail

echo Done.
echo Connect with:
echo   psql "host=%IP% user=%DB_USER% password=%ROOT_PW% dbname=customer-database sslmode=require"
echo   psql "host=%IP% user=%DB_USER% password=%ROOT_PW% dbname=product-database sslmode=require"
echo   psql "host=%IP% user=%DB_USER% password=%ROOT_PW% dbname=financial-database sslmode=require"
goto :eof

:fail
echo Script failed. Check errors above.
exit /b 1
