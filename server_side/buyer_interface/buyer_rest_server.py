import os
import sys
import grpc
from typing import List, Optional
from fastapi import FastAPI, Header, HTTPException, Body
from pydantic import BaseModel

# Add generated directory to sys.path
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.append(os.path.join(REPO_ROOT, 'generated'))

from protos import database_pb2
from protos import database_pb2_grpc
from zeep import Client as SoapClient

app = FastAPI(title="Marketplace Buyer API")

# gRPC Setup
DB_SERVICE_ADDR = os.getenv("DB_SERVICE_ADDR", "localhost:50051")
channel = grpc.insecure_channel(DB_SERVICE_ADDR)
db_stub = database_pb2_grpc.DatabaseServiceStub(channel)

# --- Models ---
class CreateAccountModel(BaseModel):
    username: str
    password: str

class LoginModel(BaseModel):
    username: str
    password: str

class AddToCartModel(BaseModel):
    item_id: int
    quantity: int

class FeedbackModel(BaseModel):
    item_id: int
    is_positive: bool

class PurchaseModel(BaseModel):
    name: str
    card_number: str
    expiration_date: str
    security_code: str

# --- Helpers ---
def verify_session(session_id: str):
    if not session_id:
        raise HTTPException(status_code=401, detail="Session ID required")
    try:
        resp = db_stub.VerifySession(database_pb2.VerifySessionRequest(session_id=session_id))
        return resp.user_id, resp.role
    except grpc.RpcError as e:
        if e.code() == grpc.StatusCode.UNAUTHENTICATED:
            raise HTTPException(status_code=401, detail="Invalid or expired session")
        raise HTTPException(status_code=500, detail=str(e))

# --- Endpoints ---

@app.post("/buyer/account")
def create_account(data: CreateAccountModel):
    try:
        resp = db_stub.CreateAccount(database_pb2.CreateAccountRequest(
            role="buyer", username=data.username, password=data.password
        ))
        return {"buyer_id": resp.user_id}
    except grpc.RpcError as e:
        raise HTTPException(status_code=400, detail=e.details())

@app.post("/buyer/login")
def login(data: LoginModel):
    try:
        resp = db_stub.AuthenticateUser(database_pb2.AuthenticateRequest(
            role="buyer", username=data.username, password=data.password
        ))
        return {"session_id": resp.session_id, "buyer_id": resp.user_id}
    except grpc.RpcError as e:
        raise HTTPException(status_code=401, detail=e.details())

@app.post("/buyer/logout")
def logout(x_session_id: str = Header(None)):
    user_id, role = verify_session(x_session_id)
    # Clear active cart on logout if not saved (PA1 requirement)
    db_stub.DeleteUnsavedCart(database_pb2.DeleteUnsavedCartRequest(
        buyer_id=user_id, session_id=x_session_id
    ))
    db_stub.DeleteSessions(database_pb2.DeleteSessionsRequest(
        session_id=x_session_id, user_id=user_id, role=role, scope="single"
    ))
    return {"status": "success"}

@app.get("/buyer/items")
def search_items(category: int = 0, keywords: str = ""):
    kw_list = [k.strip() for k in keywords.split(",") if k.strip()]
    resp = db_stub.SearchItems(database_pb2.SearchItemsRequest(
        category=category, keywords=kw_list
    ))
    items = []
    for item in resp.items:
        items.append({
            "item_id": item.item_id,
            "item_name": item.item_name,
            "category": item.category,
            "keywords": item.keywords,
            "condition_is_new": item.condition_is_new,
            "price": item.price,
            "quantity": item.quantity,
            "seller_id": item.seller_id
        })
    return {"items": items}

@app.get("/buyer/items/{item_id}")
def get_item(item_id: int):
    try:
        item = db_stub.GetItem(database_pb2.GetItemRequest(item_id=item_id))
        return {
            "item_id": item.item_id,
            "item_name": item.item_name,
            "category": item.category,
            "keywords": item.keywords,
            "condition_is_new": item.condition_is_new,
            "price": item.price,
            "quantity": item.quantity,
            "seller_id": item.seller_id
        }
    except grpc.RpcError as e:
        if e.code() == grpc.StatusCode.NOT_FOUND:
            raise HTTPException(status_code=404, detail="Item not found")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/buyer/cart")
def add_to_cart(data: AddToCartModel, x_session_id: str = Header(None)):
    user_id, _ = verify_session(x_session_id)
    # Check availability first
    try:
        item = db_stub.GetItem(database_pb2.GetItemRequest(item_id=data.item_id))
        if item.quantity < data.quantity:
            raise HTTPException(status_code=400, detail="Insufficient quantity available")
        
        db_stub.AddToCart(database_pb2.AddToCartRequest(
            buyer_id=user_id, session_id=x_session_id, item_id=data.item_id, quantity=data.quantity
        ))
        return {"status": "success"}
    except grpc.RpcError as e:
        raise HTTPException(status_code=404, detail="Item not found")

@app.get("/buyer/cart")
def display_cart(x_session_id: str = Header(None)):
    user_id, _ = verify_session(x_session_id)
    resp = db_stub.ListCart(database_pb2.ListCartRequest(
        buyer_id=user_id, session_id=x_session_id
    ))
    return {"cart": [{"item_id": i.item_id, "quantity": i.quantity} for i in resp.items]}

@app.post("/buyer/cart/save")
def save_cart(x_session_id: str = Header(None)):
    user_id, _ = verify_session(x_session_id)
    db_stub.SaveCart(database_pb2.SaveCartRequest(
        buyer_id=user_id, session_id=x_session_id
    ))
    return {"status": "success"}

@app.delete("/buyer/cart/all")
def clear_cart(x_session_id: str = Header(None)):
    user_id, _ = verify_session(x_session_id)
    db_stub.ClearCart(database_pb2.ClearCartRequest(
        buyer_id=user_id, session_id=x_session_id
    ))
    return {"status": "success"}

@app.post("/buyer/feedback")
def provide_feedback(data: FeedbackModel, x_session_id: str = Header(None)):
    user_id, _ = verify_session(x_session_id)
    db_stub.ProvideFeedback(database_pb2.ProvideFeedbackRequest(
        item_id=data.item_id, buyer_id=user_id, is_positive=data.is_positive
    ))
    return {"status": "success"}

@app.get("/seller/{seller_id}/rating")
def get_seller_rating(seller_id: int):
    resp = db_stub.GetSellerRating(database_pb2.GetSellerRatingRequest(seller_id=seller_id))
    total = resp.pos + resp.neg
    rating = resp.pos / total if total > 0 else 0
    return {"rating": rating, "pos": resp.pos, "neg": resp.neg}

@app.get("/buyer/purchases")
def get_purchases(x_session_id: str = Header(None)):
    user_id, _ = verify_session(x_session_id)
    resp = db_stub.GetPurchaseHistory(database_pb2.GetPurchaseHistoryRequest(buyer_id=user_id))
    return {"purchases": [{"item_id": r.item_id, "quantity": r.quantity, "date": r.purchased_at} for r in resp.records]}

@app.post("/buyer/purchase")
def make_purchase(data: PurchaseModel, x_session_id: str = Header(None)):
    user_id, _ = verify_session(x_session_id)

    # 1. Get saved cart (shared across sessions)
    saved = db_stub.ListSavedCart(database_pb2.ListSavedCartRequest(buyer_id=user_id))
    if not saved.items:
        raise HTTPException(status_code=400, detail="Cart not saved")

    # 2. Check stock for all items
    items_to_buy = []
    for cart_item in saved.items:
        try:
            item = db_stub.GetItem(database_pb2.GetItemRequest(item_id=cart_item.item_id))
            if item.quantity < cart_item.quantity:
                raise HTTPException(status_code=400, detail=f"Item {cart_item.item_id} out of stock")
            items_to_buy.append((item, cart_item.quantity))
        except grpc.RpcError:
            raise HTTPException(status_code=404, detail=f"Item {cart_item.item_id} not found")

    # 3. Call SOAP Financial Service
    FINANCIAL_SERVICE_WSDL = os.getenv("FINANCIAL_SERVICE_WSDL", "http://localhost:8002/?wsdl")
    try:
        soap_client = SoapClient(FINANCIAL_SERVICE_WSDL)
        success = soap_client.service.AuthorizePayment(
            username=data.name,
            card_number=data.card_number,
            expiration_date=data.expiration_date,
            security_code=data.security_code
        )
    except Exception as e:
        print(f"SOAP error: {e}")
        # If SOAP service is down, fall back to mock or fail
        raise HTTPException(status_code=503, detail="Financial service unavailable")
    
    if not success:
        raise HTTPException(status_code=402, detail="Payment authorization failed")

    # 4. Finalize Purchase
    for item, qty in items_to_buy:
        # Deduct quantity
        db_stub.UpdateItemQuantity(database_pb2.UpdateItemQuantityRequest(
            item_id=item.item_id, seller_id=item.seller_id, quantity_delta=-qty
        ))
        # Create purchase record
        db_stub.CreatePurchase(database_pb2.CreatePurchaseRequest(
            buyer_id=user_id, item_id=item.item_id, quantity=qty
        ))
        
    # 5. Clear saved cart
    db_stub.ClearSavedCart(database_pb2.ClearSavedCartRequest(buyer_id=user_id))
    
    return {"status": "success", "message": "Purchase completed successfully"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
