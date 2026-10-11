from __future__ import annotations

import argparse

from client_side.seller_interface.seller_rest_client import SellerRestClient


def main() -> None:
    parser = argparse.ArgumentParser(description="Seller REST CLI")
    parser.add_argument("host")
    parser.add_argument("port", type=int)
    args = parser.parse_args()

    client = SellerRestClient(args.host, args.port)
    print("Seller REST CLI started. Type 'help' for commands.")

    while True:
        try:
            line = input("seller> ").strip()
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
                print("register_item <name> <category> <condition> <price> <quantity> [keywords...]")
                print("change_price <item_id> <new_price>")
                print("update_qty <item_id> <delta>")
                print("list_items")
                print("get_item <item_id>")
                print("rating")
                print("quit")
            elif cmd == "create_account" and len(rest) == 2:
                seller_id = client.create_account(rest[0], rest[1])
                print(f"Account created. Seller ID: {seller_id}")
            elif cmd == "login" and len(rest) == 2:
                seller_id = client.login(rest[0], rest[1])
                print(f"Logged in. Seller ID: {seller_id} Session: {client.session_id}")
            elif cmd == "logout" and len(rest) == 0:
                client.logout()
                print("Logged out.")
            elif cmd == "register_item" and len(rest) >= 5:
                name = rest[0]
                category = int(rest[1])
                condition = rest[2]
                price = float(rest[3])
                qty = int(rest[4])
                keywords = rest[5:]
                item_id = client.register_item_for_sale(name, category, keywords, condition, price, qty)
                print(f"Item registered. ID: {item_id}")
            elif cmd == "change_price" and len(rest) == 2:
                client.change_item_price(int(rest[0]), float(rest[1]))
                print("Price updated.")
            elif cmd == "update_qty" and len(rest) == 2:
                new_qty = client.update_units_for_sale(int(rest[0]), int(rest[1]))
                print(f"Quantity updated. New quantity: {new_qty}")
            elif cmd == "list_items" and len(rest) == 0:
                for item in client.display_items_for_sale():
                    print(item)
            elif cmd == "get_item" and len(rest) == 1:
                print(client.get_item(int(rest[0])))
            elif cmd == "rating" and len(rest) == 0:
                print(client.get_rating())
            else:
                print("Invalid command or arguments. Type 'help'.")
        except Exception as exc:
            print(f"Error: {exc}")


if __name__ == "__main__":
    main()
