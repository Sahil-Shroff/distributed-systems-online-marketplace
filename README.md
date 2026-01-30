# Online Marketplace System

## System Design
The system is architected as a distributed application with four distinct server components:
1.  **Buyer Client/Server**: Handles buyer authentication, cart management, and item search.
2.  **Seller Client/Server**: Handles seller authentication and item inventory management.
3.  **Product Database**: Stores item details, inventory, and purchase history.
4.  **Customer Database**: Stores user accounts (buyers/sellers) and session data.

Communication between clients and servers is implemented using raw **TCP sockets** with a custom application-layer protocol. The protocol uses length-prefixing (4 bytes) followed by a JSON payload. The backend is **stateless**; all state (sessions, carts, items) is persisted in a PostgreSQL database, ensuring resilience to server restarts.

## Assumptions
1.  **Network Reliability**: We assume a stable network where TCP connections are reliable; error handling focuses on application-level logic rather than network partitions.
2.  **Database Availability**: A single PostgreSQL instance is running on `localhost:5434` (configurable via `.env`) and services both customer and product data.
3.  **Session Management**: Sessions are token-based. A valid `session_id` must be included in requests requiring authentication.
4.  **Security**: Passwords are currently stored in plain text as per the assignment description (to be improved in later assignments).
5.  **Concurrency**: Each client connection is handled independently, allowing multiple active sessions.
6.  **Single Item Category**: Search semantics assume simple keyword matching and exact category filtering.
7.  **Inventory**: Items are decremented immediately upon "Add to Cart" or "Purchase" depending on the implementation flow (current logic checks stock on add).
8.  **Feedback**: Feedback is binary (thumbs up/down) and aggregated simply as counts.

## Current State of the System
### Working Features
-   **TCP Communication**: Robust `TCPClient` and server request handling loop.
-   **APIs**: Most core APIs are implemented:
    -   Buyer: Login, Search, Cart Management (Add/Remove/Clear/Display), Feedback.
    -   Seller: Login, Register Item, Update Price/Stock.
-   **CLI**: Fully functional command-line interfaces for both Buyer and Seller.
-   **Database Integration**: Code is structure to use `psycopg2` for PostgreSQL interactions.

### Limitations & Missing Features
-   **Purchase**: The `MakePurchase` API is a stub, as allowed by the assignment requirements.

## How to Run
1.  Ensure PostgreSQL is running on port `5434`.
2.  Start the Seller Server:
    ```bash
    python server_side/seller_interface/seller_server.py
    ```
3.  Start the Buyer Server:
    ```bash
    python server_side/buyer_interface/buyer_server.py
    ```
4.  Run Clients:
    ```bash
    python client_side/seller_interface/seller_cli.py localhost 8080
    python client_side/buyer_interface/buyer_cli.py localhost 8081
    ```