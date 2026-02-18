import sys
import requests
from client_side.seller_interface.seller_rest_client import SellerRESTClient

HELP_TEXT = """
Available commands:

Account / Session:
  create_account <username> <password>
  login <username> <password>
  logout
  rating

Items:
  register <name> <cat> <price> <qty> [kw1 kw2...]
  update_price <item_id> <new_price>
  update_qty <item_id> <delta>
  display_items

Utility:
  help
  exit
"""

def main():
    if len(sys.argv) != 2:
        print("Usage: python seller_rest_cli.py <server_url>")
        sys.exit(1)

    url = sys.argv[1].rstrip("/")
    client = SellerRESTClient(url)

    print(f"Seller REST CLI started (URL: {url}). Type 'help' for commands.")

    while True:
        try:
            raw = input("seller> ").strip()
            if not raw: continue
            parts = raw.split()
            cmd = parts[0].lower()
            args = parts[1:]

            if cmd == "help": print(HELP_TEXT)
            elif cmd == "exit": break
            elif cmd == "create_account":
                print(f"Account ID: {client.create_account(args[0], args[1])}")
            elif cmd == "login":
                print(f"Session ID: {client.login(args[0], args[1])}")
            elif cmd == "logout":
                print(client.logout())
            elif cmd == "rating":
                print(client.get_seller_rating())
            elif cmd == "register":
                name, cat, price, qty = args[0], int(args[1]), float(args[2]), int(args[3])
                kws = args[4:]
                # Note: condition is missing from simplistic CLI register command, default to 'new'
                print(f"Item ID: {client.register_item(name, cat, kws, 'new', price, qty)}")
            elif cmd == "update_price":
                print(client.update_price(int(args[0]), float(args[1])))
            elif cmd == "update_qty":
                print(client.update_quantity(int(args[0]), int(args[1])))
            elif cmd == "display_items":
                for it in client.display_items(): print(it)
            else:
                print("Unknown command.")
        except requests.exceptions.HTTPError as e:
            print(f"HTTP Error: {e.response.json().get('detail', e)}")
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    main()
