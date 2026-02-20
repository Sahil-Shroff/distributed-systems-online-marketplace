import sys
from client_side.seller_interface.seller_rest_client import SellerRestClient


def main():
    if len(sys.argv) < 3:
        print("Usage: seller_rest_cli.py <host> <port>")
        sys.exit(1)

    host = sys.argv[1]
    port = int(sys.argv[2])
    client = SellerRestClient(host, port)

    print("Seller REST CLI started. Type 'help' for commands.")
    while True:
        try:
            line = input("seller> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nExiting.")
            break

        if not line:
            continue

        parts = line.split()
        cmd = parts[0].lower()
        args = parts[1:]

        try:
            if cmd == "help":
                print("Commands:")
                print("  create_account <username> <password>")
                print("  login <username> <password>")
                print("  logout")
                print("  register_item <name> <category> <condition> <price> <quantity> <keyword1> [keyword2 ...]")
                print("  change_price <item_id> <new_price>")
                print("  update_qty <item_id> <delta>")
                print("  list_items")
                print("  rating")
                print("  quit")
            elif cmd == "quit" or cmd == "exit":
                break
            elif cmd == "create_account" and len(args) == 2:
                seller_id = client.create_account(args[0], args[1])
                print(f"Account created. Seller ID: {seller_id}")
            elif cmd == "login" and len(args) == 2:
                seller_id = client.login(args[0], args[1])
                print(f"Logged in. Seller ID: {seller_id} Session: {client.session_id}")
            elif cmd == "logout":
                client.logout()
                print("Logged out.")
            elif cmd == "register_item" and len(args) >= 6:
                name = args[0]
                category = int(args[1])
                condition = args[2]
                price = float(args[3])
                qty = int(args[4])
                keywords = args[5:]
                item_id = client.register_item_for_sale(name, category, keywords, condition, price, qty)
                print(f"Item registered. ID: {item_id}")
            elif cmd == "change_price" and len(args) == 2:
                client.change_item_price(int(args[0]), float(args[1]))
                print("Price updated.")
            elif cmd == "update_qty" and len(args) == 2:
                new_qty = client.update_units_for_sale(int(args[0]), int(args[1]))
                print(f"Quantity updated. New quantity: {new_qty}")
            elif cmd == "list_items":
                items = client.display_items_for_sale()
                for i in items:
                    print(i)
            elif cmd == "rating":
                print(client.get_rating())
            else:
                print("Invalid command or arguments. Type 'help'.")
        except Exception as e:
            print(f"Error: {e}")


if __name__ == "__main__":
    main()
