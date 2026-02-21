import sys
from client_side.common.tcp_client import TCPClient
from client_side.buyer_interface.buyer_client import BuyerClient
from client_side.common.protocol import ClientProtocolError


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
  remove_from_cart <item_id> <quantity>
  display_cart
  clear_cart
  save_cart

Feedback / History:
  feedback <item_id> <up|down>
  seller_rating <seller_id>
  purchase <name> <card_number> <expiration_date> <security_code>
  purchases

Utility:
  help
  exit
"""


def main():
    if len(sys.argv) != 3:
        print("Usage: python buyer_cli.py <server_host> <server_port>")
        sys.exit(1)

    host = sys.argv[1]
    port = int(sys.argv[2])

    tcp = TCPClient(host, port)
    client = BuyerClient(tcp)

    print("Buyer CLI started. Type 'help' for commands.")

    while True:
        try:
            raw = input("buyer> ").strip()
            if not raw:
                continue

            parts = raw.split()
            cmd = parts[0].lower()
            args = parts[1:]

            # ---------- Utility ----------
            if cmd == "help":
                print(HELP_TEXT)

            elif cmd == "exit":
                client.logout() if client.session_id else None
                tcp.close()
                print("Goodbye.")
                break

            # ---------- Account ----------
            elif cmd == "create_account":
                username, password = args
                buyer_id = client.create_account(username, password)
                print(f"Account created. Buyer ID: {buyer_id}")

            elif cmd == "login":
                username, password = args
                session_id = client.login(username, password)
                print(f"Logged in. Session ID: {session_id}")

            elif cmd == "logout":
                client.logout()
                print("Logged out.")

            # ---------- Browsing ----------
            elif cmd == "search":
                category = int(args[0])
                keywords = args[1:]
                items = client.search_items(category, keywords)
                if not items:
                    print("No items found.")
                else:
                    for it in items:
                        print(it)

            elif cmd == "get_item":
                item_id = args[0]
                item = client.get_item(item_id)
                print(item)

            # ---------- Cart ----------
            elif cmd == "add_to_cart":
                item_id, qty = args
                cart = client.add_item_to_cart(item_id, int(qty))
                print("Cart updated:", cart)

            elif cmd == "remove_from_cart":
                item_id, qty = args
                cart = client.remove_item_from_cart(item_id, int(qty))
                print("Cart updated:", cart)

            elif cmd == "display_cart":
                cart = client.display_cart()
                print("Current cart:", cart)

            elif cmd == "clear_cart":
                client.clear_cart()
                print("Cart cleared.")

            elif cmd == "save_cart":
                client.save_cart()
                print("Cart saved.")

            # ---------- Feedback / History ----------
            elif cmd == "feedback":
                item_id = args[0]
                thumbs_up = args[1].lower() == "up"
                client.provide_feedback(item_id, thumbs_up)
                print("Feedback submitted.")

            elif cmd == "seller_rating":
                seller_id = int(args[0])
                rating = client.get_seller_rating(seller_id)
                print("Seller rating:", rating)

            elif cmd == "purchases":
                items = client.get_purchase_history()
                print("Purchased items:", items)

            elif cmd == "purchase":
                if len(args) != 4:
                    print("Usage: purchase <name> <card_number> <expiration_date> <security_code>")
                else:
                    name, card_number, exp, cvv = args
                    result = client.make_purchase(name, card_number, exp, cvv)
                    print("Purchase result:", result)

            else:
                print("Unknown command. Type 'help'.")

        except ClientProtocolError as e:
            print(f"Error {e}")

        except (ValueError, IndexError):
            print("Invalid command or arguments. Type 'help'.")

        except KeyboardInterrupt:
            print("\nExiting.")
            tcp.close()
            break


if __name__ == "__main__":
    main()
