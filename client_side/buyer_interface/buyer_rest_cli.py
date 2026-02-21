import sys
from client_side.buyer_interface.buyer_rest_client import BuyerRestClient


def main():
    if len(sys.argv) < 3:
        print("Usage: buyer_rest_cli.py <host> <port>")
        sys.exit(1)

    host = sys.argv[1]
    port = int(sys.argv[2])
    client = BuyerRestClient(host, port)

    print("Buyer REST CLI started. Type 'help' for commands.")
    while True:
        try:
            line = input("buyer> ").strip()
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
                print("  search [category] [kw1 kw2 ...]")
                print("  get_item <item_id>")
                print("  add_to_cart <item_id> <qty>")
                print("  display_cart")
                print("  save_cart")
                print("  clear_cart")
                print("  feedback <item_id> <up|down>")
                print("  purchase <name> <card> <exp> <cvv>")
                print("  quit")
            elif cmd in ("quit", "exit"):
                break
            elif cmd == "create_account" and len(args) == 2:
                bid = client.create_account(args[0], args[1])
                print(f"Account created. Buyer ID: {bid}")
            elif cmd == "login" and len(args) == 2:
                bid = client.login(args[0], args[1])
                print(f"Logged in. Buyer ID: {bid} Session: {client.session_id}")
            elif cmd == "logout":
                client.logout()
                print("Logged out.")
            elif cmd == "search":
                category = int(args[0]) if args else 0
                keywords = args[1:] if len(args) > 1 else []
                items = client.search_items(category=category, keywords=keywords)
                for i in items:
                    print(i)
            elif cmd == "get_item" and len(args) == 1:
                print(client.get_item(int(args[0])))
            elif cmd == "add_to_cart" and len(args) == 2:
                client.add_to_cart(int(args[0]), int(args[1]))
                print("Cart updated.")
            elif cmd == "display_cart":
                print("Current cart:", client.display_cart())
            elif cmd == "save_cart":
                client.save_cart()
                print("Cart saved.")
            elif cmd == "clear_cart":
                client.clear_cart()
                print("Cart cleared.")
            elif cmd == "feedback" and len(args) == 2:
                is_up = args[1].lower() in ("up", "thumbs_up", "positive", "1", "true")
                client.provide_feedback(int(args[0]), is_up)
                print("Feedback recorded.")
            elif cmd == "purchase" and len(args) == 4:
                res = client.purchase(args[0], args[1], args[2], args[3])
                print("Purchase result:", res)
            else:
                print("Invalid command or arguments. Type 'help'.")
        except Exception as e:
            print(f"Error: {e}")


if __name__ == "__main__":
    main()
