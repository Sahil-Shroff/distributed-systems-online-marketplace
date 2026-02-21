import argparse
import sys
from pathlib import Path

# Ensure repo root on sys.path for module imports
REPO_ROOT = Path(__file__).resolve().parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from server_side.seller_interface.seller_server import SellerServer
from server_side.buyer_interface.buyer_server import BuyerServer
from server_side.buyer_interface import buyer_rest_server
from server_side.seller_interface import seller_rest_server
from client_side.common.tcp_client import TCPClient
from client_side.seller_interface.seller_client import SellerClient
from client_side.buyer_interface.buyer_client import BuyerClient
import client_side.seller_interface.seller_cli as seller_cli
import client_side.buyer_interface.buyer_cli as buyer_cli
import client_side.seller_interface.seller_rest_cli as seller_rest_cli
import client_side.buyer_interface.buyer_rest_cli as buyer_rest_cli
import uvicorn


def run_seller_server(args):
    server = SellerServer(args.host, args.port)
    try:
        server.start()
    except KeyboardInterrupt:
        print("Shutting down seller server...")
        server.stop()


def run_buyer_server(args):
    server = BuyerServer(args.host, args.port)
    try:
        server.start()
    except KeyboardInterrupt:
        print("Shutting down buyer server...")
        server.stop()


def run_buyer_rest_server(args):
    uvicorn.run(
        buyer_rest_server.app,
        host=args.host,
        port=args.port,
        reload=False,
    )


def run_seller_rest_server(args):
    uvicorn.run(
        seller_rest_server.app,
        host=args.host,
        port=args.port,
        reload=False,
    )


def run_seller_client(args):
    tcp = TCPClient(args.host, args.port)
    client = SellerClient(tcp)
    print(f"Seller client connected to {args.host}:{args.port}. Use the CLI for interactive commands.")
    tcp.close()


def run_buyer_client(args):
    tcp = TCPClient(args.host, args.port)
    client = BuyerClient(tcp)
    print(f"Buyer client connected to {args.host}:{args.port}. Use the CLI for interactive commands.")
    tcp.close()


def run_seller_cli(args):
    sys.argv = ["seller_cli.py", args.host, str(args.port)]
    seller_cli.main()

def run_seller_rest_cli(args):
    sys.argv = ["seller_rest_cli.py", args.host, str(args.port)]
    seller_rest_cli.main()


def run_buyer_cli(args):
    sys.argv = ["buyer_cli.py", args.host, str(args.port)]
    buyer_cli.main()

def run_buyer_rest_cli(args):
    sys.argv = ["buyer_rest_cli.py", args.host, str(args.port)]
    buyer_rest_cli.main()


def main():
    parser = argparse.ArgumentParser(description="Run marketplace components.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    # seller server
    p = sub.add_parser("seller-server", help="Run seller server")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8080)
    p.set_defaults(func=run_seller_server)

    # buyer server
    p = sub.add_parser("buyer-server", help="Run buyer server")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8081)
    p.set_defaults(func=run_buyer_server)

    # seller client demo
    p = sub.add_parser("seller-client", help="Run seller client demo (minimal)")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8080)
    p.set_defaults(func=run_seller_client)

    # buyer client demo
    p = sub.add_parser("buyer-client", help="Run buyer client demo (minimal)")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8081)
    p.set_defaults(func=run_buyer_client)

    # seller CLI
    p = sub.add_parser("seller-cli", help="Run seller CLI")
    p.add_argument("host")
    p.add_argument("port", type=int)
    p.set_defaults(func=run_seller_cli)

    # seller REST CLI
    p = sub.add_parser("seller-rest-cli", help="Run seller REST CLI")
    p.add_argument("host")
    p.add_argument("port", type=int)
    p.set_defaults(func=run_seller_rest_cli)

    # buyer REST CLI
    p = sub.add_parser("buyer-rest-cli", help="Run buyer REST CLI")
    p.add_argument("host")
    p.add_argument("port", type=int)
    p.set_defaults(func=run_buyer_rest_cli)

    # buyer CLI
    p = sub.add_parser("buyer-cli", help="Run buyer CLI")
    p.add_argument("host")
    p.add_argument("port", type=int)
    p.set_defaults(func=run_buyer_cli)

    # buyer REST server (FastAPI)
    p = sub.add_parser("buyer-rest-server", help="Run buyer REST server (FastAPI)")
    p.add_argument("--host", default="0.0.0.0")
    p.add_argument("--port", type=int, default=8001)
    p.set_defaults(func=run_buyer_rest_server)

    # seller REST server (FastAPI)
    p = sub.add_parser("seller-rest-server", help="Run seller REST server (FastAPI)")
    p.add_argument("--host", default="0.0.0.0")
    p.add_argument("--port", type=int, default=8000)
    p.set_defaults(func=run_seller_rest_server)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
