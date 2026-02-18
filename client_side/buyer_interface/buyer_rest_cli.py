import sys
import requests
from client_side.buyer_interface.buyer_rest_client import BuyerRESTClient

HELP_TEXT = """
Available commands:

Account / Session:
  create_account <username> <password>
  login <username> <password>
  logout

Browsing:
  search <category> <kw1> [kw2 kw3 kw4 kw5]
  get_item <item_id>

Cart:
  add_to_cart <item_id> <quantity>
  display_cart
  clear_cart
  save_cart

Purchase:
  make_purchase

Feedback / History:
  feedback <item_id> <up|down>
  seller_rating <seller_id>
  purchases

Utility:
  help
  exit
"""

def main():
    if len(sys.argv) != 2:
        print("Usage: python buyer_rest_cli.py <server_url>")
        print("Example: python buyer_rest_cli.py http://localhost:8001")
        sys.exit(1)

    url = sys.argv[1].rstrip("/")
    client = BuyerRESTClient(url)

    print(f"Buyer REST CLI started (URL: {url}). Type 'help' for commands.")

    while True:
        try:
            raw = input("buyer> ").strip()
            if not raw:
                continue

            parts = raw.split()
            cmd = parts[0].lower()
            args = parts[1:]

            if cmd == "help":
                print(HELP_TEXT)
            elif cmd == "exit":
                break
            elif cmd == "create_account":
                username, password = args
                bid = client.create_account(username, password)
                print(f"Account created. Buyer ID: {bid}")
            elif cmd == "login":
                username, password = args
                sid = client.login(username, password)
                print(f"Logged in. Session ID: {sid}")
            elif cmd == "logout":
                client.logout()
                print("Logged out.")
            elif cmd == "search":
                category = int(args[0])
                keywords = args[1:]
                items = client.search_items(category, keywords)
                for it in items: print(it)
            elif cmd == "get_item":
                print(client.get_item(int(args[0])))
            elif cmd == "add_to_cart":
                item_id, qty = map(int, args)
                print(client.add_item_to_cart(item_id, qty))
            elif cmd == "display_cart":
                print("Cart:", client.display_cart())
            elif cmd == "clear_cart":
                print(client.clear_cart())
            elif cmd == "save_cart":
                print(client.save_cart())
            elif cmd == "make_purchase":
                name = input("Cardholder Name: ")
                card = input("Card Number: ")
                expiry = input("Expiration Date (MM/YY): ")
                cvv = input("Security Code: ")
                result = client.make_purchase(name, card, expiry, cvv)
                print(result["message"])
            elif cmd == "feedback":
                client.provide_feedback(int(args[0]), args[1].lower() == "up")
                print("Feedback submitted.")
            elif cmd == "seller_rating":
                print(client.get_seller_rating(int(args[0])))
            elif cmd == "purchases":
                print(client.get_purchase_history())
            else:
                print("Unknown command.")
        except requests.exceptions.HTTPError as e:
            print(f"HTTP Error: {e.response.json().get('detail', e)}")
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    main()
