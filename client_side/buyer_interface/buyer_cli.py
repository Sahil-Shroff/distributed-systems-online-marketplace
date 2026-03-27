from __future__ import annotations

import argparse

from client_side.buyer_interface.buyer_rest_client import BuyerRestClient


def main() -> None:
    parser = argparse.ArgumentParser(description="Buyer REST CLI")
    parser.add_argument("host")
    parser.add_argument("port", type=int)
    args = parser.parse_args()

    client = BuyerRestClient(args.host, args.port)
    print("Buyer REST CLI started. Type 'help' for commands.")

    while True:
        try:
            line = input("buyer> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not line:
            continue

        parts = line.split()
        cmd = parts[0].lower()
        rest = parts[1:]

        try:
            if cmd in {"quit", "exit"}:
                break
            if cmd == "help":
                print("create_account <username> <password>")
                print("login <username> <password>")
                print("logout")
                print("search [category] [keyword1 keyword2 ...]")
                print("get_item <item_id>")
                print("add_to_cart <item_id> <quantity>")
                print("remove_from_cart <item_id>")
                print("display_cart")
                print("save_cart")
                print("clear_cart")
                print("feedback <item_id> <up|down>")
                print("purchase_history")
                print("purchase <username> <credit_card_number> <expiration_date> <security_code>")
                print("quit")
            elif cmd == "create_account" and len(rest) == 2:
                buyer_id = client.create_account(rest[0], rest[1])
                print(f"Account created. Buyer ID: {buyer_id}")
            elif cmd == "login" and len(rest) == 2:
                buyer_id = client.login(rest[0], rest[1])
                print(f"Logged in. Buyer ID: {buyer_id} Session: {client.session_id}")
            elif cmd == "logout" and len(rest) == 0:
                client.logout()
                print("Logged out.")
            elif cmd == "search":
                category = int(rest[0]) if rest else 0
                keywords = rest[1:] if rest else []
                for item in client.search_items(category=category, keywords=keywords):
                    print(item)
            elif cmd == "get_item" and len(rest) == 1:
                print(client.get_item(int(rest[0])))
            elif cmd == "add_to_cart" and len(rest) == 2:
                client.add_to_cart(int(rest[0]), int(rest[1]))
                print("Cart updated.")
            elif cmd == "remove_from_cart" and len(rest) == 1:
                client.remove_from_cart(int(rest[0]))
                print("Item removed from cart.")
            elif cmd == "display_cart" and len(rest) == 0:
                print(client.display_cart())
            elif cmd == "save_cart" and len(rest) == 0:
                client.save_cart()
                print("Cart saved.")
            elif cmd == "clear_cart" and len(rest) == 0:
                client.clear_cart()
                print("Cart cleared.")
            elif cmd == "feedback" and len(rest) == 2:
                client.provide_feedback(int(rest[0]), rest[1].lower() == "up")
                print("Feedback submitted.")
            elif cmd == "purchase_history" and len(rest) == 0:
                print(client.get_purchase_history())
            elif cmd == "purchase" and len(rest) == 4:
                print(client.make_purchase(rest[0], rest[1], rest[2], rest[3]))
            else:
                print("Invalid command or arguments. Type 'help'.")
        except Exception as exc:
            print(f"Error: {exc}")


if __name__ == "__main__":
    main()
