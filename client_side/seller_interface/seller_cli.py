import sys
from pathlib import Path

# ensure repo root on path for client_side imports
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from client_side.common.tcp_client import TCPClient
from client_side.seller_interface.seller_client import SellerClient
from client_side.common.protocol import ClientProtocolError


HELP_TEXT = """
Available commands:

Account / Session:
  create_account <username> <password>
  login <username> <password>
  logout

Item Management:
  register_item <name> <category> <condition> <price> <quantity> <kw1> [kw2 kw3 kw4 kw5]
  change_price <item_id> <new_price>
  update_units <item_id> <quantity_to_remove>
  display_items

Utility:
  help
  exit
"""


def main():
    if len(sys.argv) != 3:
        print("Usage: python seller_cli.py <server_host> <server_port>")
        sys.exit(1)

    host = sys.argv[1]
    port = int(sys.argv[2])

    tcp = TCPClient(host, port)
    client = SellerClient(tcp)

    print("Seller CLI started. Type 'help' for commands.")

    while True:
        try:
            raw = input("seller> ").strip()
            if not raw:
                continue

            parts = raw.split()
            print("parts", parts)
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
                seller_id = client.create_account(username, password)
                print(f"Account created. Seller ID: {seller_id}")

            elif cmd == "login":
                username, password = args
                seller_id = client.login(username, password)
                print(f"Logged in. Seller ID: {seller_id}")

            elif cmd == "logout":
                client.logout()
                print("Logged out.")

            # ---------- Item Management ----------
            elif cmd == "register_item":
                name = args[0]
                category = int(args[1])
                condition = args[2]
                price = float(args[3])
                quantity = int(args[4])
                keywords = args[5:]

                item_id = client.register_item_for_sale(
                    item_name=name,
                    category=category,
                    keywords=keywords,
                    condition=condition,
                    price=price,
                    quantity=quantity
                )
                print(f"Item registered. Item ID: {item_id}")

            elif cmd == "change_price":
                item_id = args[0]
                new_price = float(args[1])
                client.change_item_price(item_id, new_price)
                print("Price updated.")

            elif cmd == "update_units":
                item_id = args[0]
                delta = int(args[1])
                client.update_units_for_sale(item_id, delta)
                print("Units updated.")

            elif cmd == "display_items":
                items = client.display_items_for_sale()
                if not items:
                    print("No items currently for sale.")
                else:
                    for it in items:
                        print(it)

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
