import os
import random
import psycopg2
from psycopg2.pool import SimpleConnectionPool
from spyne import Application, rpc, ServiceBase, Unicode, Boolean
from spyne.protocol.soap import Soap11
from spyne.server.wsgi import WsgiApplication
from wsgiref.simple_server import make_server


def _init_db_pool():
    host = os.getenv("FIN_DB_HOST", "localhost")
    port = int(os.getenv("FIN_DB_PORT", "5434"))
    dbname = os.getenv("FIN_DB_NAME", "financial-database")
    user = os.getenv("FIN_DB_USER", "postgres")
    password = os.getenv("FIN_DB_PASSWORD", "password")
    maxconn = int(os.getenv("FIN_DB_POOL_MAX", "5"))
    try:
        pool = SimpleConnectionPool(
            minconn=1,
            maxconn=maxconn,
            host=host,
            port=port,
            dbname=dbname,
            user=user,
            password=password,
        )
        # Ensure table exists
        conn = pool.getconn()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS transactions (
                    id SERIAL PRIMARY KEY,
                    username VARCHAR(128) NOT NULL,
                    card_last4 VARCHAR(4) NOT NULL,
                    expiration_date VARCHAR(10) NOT NULL,
                    approved BOOLEAN NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
                """
            )
            conn.commit()
            cur.close()
        finally:
            pool.putconn(conn)
        print("[financial_service] DB pool initialized")
        return pool
    except Exception as e:
        print(f"[financial_service] DB init failed, logging disabled: {e}")
        return None


DB_POOL = _init_db_pool()

class FinancialTransactionService(ServiceBase):
    @rpc(Unicode, Unicode, Unicode, Unicode, _returns=Boolean)
    def AuthorizePayment(self, username, card_number, expiration_date, security_code):
        print(f"Auth request for {username} (Card: {card_number})")
        # 90% probability of Success
        approved = random.random() < 0.9
        if DB_POOL:
            conn = None
            try:
                conn = DB_POOL.getconn()
                cur = conn.cursor()
                cur.execute(
                    """
                    INSERT INTO transactions (username, card_last4, expiration_date, approved)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (username, card_number[-4:], expiration_date, approved),
                )
                conn.commit()
                cur.close()
            except Exception as e:
                print(f"[financial_service] log insert failed: {e}")
                if conn:
                    conn.rollback()
            finally:
                if conn:
                    DB_POOL.putconn(conn)
        return approved

application = Application(
    [FinancialTransactionService],
    tns='marketplace.financial.soap',
    in_protocol=Soap11(validator='lxml'),
    out_protocol=Soap11()
)

if __name__ == '__main__':
    wsgi_app = WsgiApplication(application)
    server = make_server('0.0.0.0', 8002, wsgi_app)
    print("SOAP Financial Service starting on port 8002...")
    print("WSDL is available at: http://localhost:8002/?wsdl")
    server.serve_forever()
