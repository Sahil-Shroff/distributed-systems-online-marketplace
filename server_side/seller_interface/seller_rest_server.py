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

app = FastAPI(title="Marketplace Seller API")

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

class RegisterItemModel(BaseModel):
    item_name: str
    category: int
    keywords: List[str]
    condition: str
    price: float
    quantity: int

class UpdatePriceModel(BaseModel):
    price: float

class UpdateQuantityModel(BaseModel):
    quantity_delta: int

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

@app.post("/seller/account")
def create_account(data: CreateAccountModel):
    try:
        resp = db_stub.CreateAccount(database_pb2.CreateAccountRequest(
            role="seller", username=data.username, password=data.password
        ))
        return {"seller_id": resp.user_id}
    except grpc.RpcError as e:
        raise HTTPException(status_code=400, detail=e.details())

@app.post("/seller/login")
def login(data: LoginModel):
    try:
        resp = db_stub.AuthenticateUser(database_pb2.AuthenticateRequest(
            role="seller", username=data.username, password=data.password
        ))
        return {"session_id": resp.session_id, "seller_id": resp.user_id}
    except grpc.RpcError as e:
        raise HTTPException(status_code=401, detail=e.details())

@app.post("/seller/logout")
def logout(x_session_id: str = Header(None)):
    user_id, role = verify_session(x_session_id)
    db_stub.DeleteSessions(database_pb2.DeleteSessionsRequest(
        session_id=x_session_id, user_id=user_id, role=role, scope="single"
    ))
    return {"status": "success"}

@app.get("/seller/rating")
def get_seller_rating(x_session_id: str = Header(None)):
    user_id, _ = verify_session(x_session_id)
    resp = db_stub.GetSellerRating(database_pb2.GetSellerRatingRequest(seller_id=user_id))
    total = resp.pos + resp.neg
    rating = float(resp.pos) / total if total > 0 else 0.0
    return {"rating": rating, "pos": int(resp.pos), "neg": int(resp.neg)}

@app.post("/seller/items")
def register_item(data: RegisterItemModel, x_session_id: str = Header(None)):
    user_id, _ = verify_session(x_session_id)
    resp = db_stub.RegisterItem(database_pb2.RegisterItemRequest(
        item_name=data.item_name,
        category=data.category,
        keywords=data.keywords,
        condition=data.condition,
        price=data.price,
        quantity=data.quantity,
        seller_id=user_id
    ))
    return {"item_id": resp.item_id}

@app.put("/seller/items/{item_id}/price")
def update_price(item_id: int, data: UpdatePriceModel, x_session_id: str = Header(None)):
    user_id, _ = verify_session(x_session_id)
    try:
        db_stub.UpdateItemPrice(database_pb2.UpdateItemPriceRequest(
            item_id=item_id, seller_id=user_id, price=data.price
        ))
        return {"status": "success"}
    except grpc.RpcError as e:
        if e.code() == grpc.StatusCode.NOT_FOUND:
            raise HTTPException(status_code=404, detail="Item not found or unauthorized")
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/seller/items/{item_id}/quantity")
def update_quantity(item_id: int, data: UpdateQuantityModel, x_session_id: str = Header(None)):
    user_id, _ = verify_session(x_session_id)
    try:
        resp = db_stub.UpdateItemQuantity(database_pb2.UpdateItemQuantityRequest(
            item_id=item_id, seller_id=user_id, quantity_delta=data.quantity_delta
        ))
        return {"status": "success", "new_quantity": resp.new_quantity}
    except grpc.RpcError as e:
        if e.code() == grpc.StatusCode.NOT_FOUND:
            raise HTTPException(status_code=404, detail="Item not found or unauthorized")
        if e.code() == grpc.StatusCode.FAILED_PRECONDITION:
            raise HTTPException(status_code=400, detail="Insufficient quantity")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/seller/items")
def display_items(x_session_id: str = Header(None)):
    user_id, _ = verify_session(x_session_id)
    resp = db_stub.GetItemsBySeller(database_pb2.GetItemsBySellerRequest(seller_id=user_id))
    items = []
    for item in resp.items:
        items.append({
            "item_id": item.item_id,
            "item_name": item.item_name,
            "category": item.category,
            "keywords": list(item.keywords),
            "condition_is_new": item.condition_is_new,
            "price": item.price,
            "quantity": item.quantity
        })
    return {"items": items}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
