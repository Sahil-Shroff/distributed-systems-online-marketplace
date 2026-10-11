import os
import sys

import grpc
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.append(os.path.join(REPO_ROOT, "generated"))

from protos import database_pb2
from protos import database_pb2_grpc

app = FastAPI(title="Marketplace Seller API")

DEFAULT_DB_ADDR = os.getenv("DB_SERVICE_ADDR", "localhost:50051")
CUSTOMER_SERVICE_ADDRS = [addr.strip() for addr in os.getenv("CUSTOMER_SERVICE_ADDR", DEFAULT_DB_ADDR).split(",") if addr.strip()]
PRODUCT_SERVICE_ADDRS = [addr.strip() for addr in os.getenv("PRODUCT_SERVICE_ADDR", DEFAULT_DB_ADDR).split(",") if addr.strip()]
customer_stubs = [database_pb2_grpc.DatabaseServiceStub(grpc.insecure_channel(addr)) for addr in CUSTOMER_SERVICE_ADDRS]
product_stubs = [database_pb2_grpc.DatabaseServiceStub(grpc.insecure_channel(addr)) for addr in PRODUCT_SERVICE_ADDRS]


class CreateAccountModel(BaseModel):
    username: str
    password: str


class LoginModel(BaseModel):
    username: str
    password: str


class RegisterItemModel(BaseModel):
    item_name: str
    category: int
    keywords: list[str]
    condition: str
    price: float
    quantity: int


class UpdatePriceModel(BaseModel):
    price: float


class UpdateQuantityModel(BaseModel):
    quantity_delta: int


def _grpc_call(stubs, method_name: str, request, timeout: float = 5.0):
    last_error = None
    for stub in stubs:
        try:
            return getattr(stub, method_name)(request, timeout=timeout)
        except grpc.RpcError as exc:
            last_error = exc
            if exc.code() in {grpc.StatusCode.UNAVAILABLE, grpc.StatusCode.DEADLINE_EXCEEDED, grpc.StatusCode.UNKNOWN}:
                continue
            raise
    if last_error is not None:
        raise last_error
    raise RuntimeError(f"No stubs configured for {method_name}")


def _grpc_read_call(stubs, method_name: str, request, timeout: float = 5.0, *, empty_attr: str | None = None):
    last_error = None
    last_response = None
    for stub in stubs:
        try:
            response = getattr(stub, method_name)(request, timeout=timeout)
            last_response = response
            if empty_attr is not None and not getattr(response, empty_attr):
                continue
            return response
        except grpc.RpcError as exc:
            last_error = exc
            if exc.code() in {
                grpc.StatusCode.UNAVAILABLE,
                grpc.StatusCode.DEADLINE_EXCEEDED,
                grpc.StatusCode.UNKNOWN,
                grpc.StatusCode.NOT_FOUND,
            }:
                continue
            raise
    if last_response is not None:
        return last_response
    if last_error is not None:
        raise last_error
    raise RuntimeError(f"No stubs configured for {method_name}")


def verify_session(session_id: str):
    if not session_id:
        raise HTTPException(status_code=401, detail="Session ID required")
    try:
        resp = _grpc_call(customer_stubs, "VerifySession", database_pb2.VerifySessionRequest(session_id=session_id))
        return resp.user_id, resp.role
    except grpc.RpcError as e:
        if e.code() == grpc.StatusCode.UNAUTHENTICATED:
            raise HTTPException(status_code=401, detail="Invalid or expired session")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/seller/account")
def create_account(data: CreateAccountModel):
    try:
        resp = _grpc_call(
            customer_stubs,
            "CreateAccount",
            database_pb2.CreateAccountRequest(role="seller", username=data.username, password=data.password),
        )
        return {"seller_id": resp.user_id}
    except grpc.RpcError as e:
        raise HTTPException(status_code=400, detail=e.details())


@app.post("/seller/login")
def login(data: LoginModel):
    try:
        resp = _grpc_call(
            customer_stubs,
            "AuthenticateUser",
            database_pb2.AuthenticateRequest(role="seller", username=data.username, password=data.password),
        )
        return {"session_id": resp.session_id, "seller_id": resp.user_id}
    except grpc.RpcError as e:
        raise HTTPException(status_code=401, detail=e.details())


@app.post("/seller/logout")
def logout(x_session_id: str = Header(None)):
    user_id, role = verify_session(x_session_id)
    _grpc_call(
        customer_stubs,
        "DeleteSessions",
        database_pb2.DeleteSessionsRequest(session_id=x_session_id, user_id=user_id, role=role, scope="single"),
    )
    return {"status": "success"}


@app.get("/seller/rating")
def get_seller_rating(x_session_id: str = Header(None)):
    user_id, _ = verify_session(x_session_id)
    resp = _grpc_call(customer_stubs, "GetSellerRating", database_pb2.GetSellerRatingRequest(seller_id=user_id))
    total = resp.pos + resp.neg
    rating = float(resp.pos) / total if total > 0 else 0.0
    return {"rating": rating, "pos": int(resp.pos), "neg": int(resp.neg)}


@app.post("/seller/items")
def register_item(data: RegisterItemModel, x_session_id: str = Header(None)):
    user_id, _ = verify_session(x_session_id)
    resp = _grpc_call(
        product_stubs,
        "RegisterItem",
        database_pb2.RegisterItemRequest(
            item_name=data.item_name,
            category=data.category,
            keywords=data.keywords,
            condition=data.condition,
            price=data.price,
            quantity=data.quantity,
            seller_id=user_id,
        ),
        timeout=10.0,
    )
    return {"item_id": resp.item_id}


@app.put("/seller/items/{item_id}/price")
def update_price(item_id: int, data: UpdatePriceModel, x_session_id: str = Header(None)):
    user_id, _ = verify_session(x_session_id)
    try:
        _grpc_call(
            product_stubs,
            "UpdateItemPrice",
            database_pb2.UpdateItemPriceRequest(item_id=item_id, seller_id=user_id, price=data.price),
            timeout=10.0,
        )
        return {"status": "success"}
    except grpc.RpcError as e:
        if e.code() == grpc.StatusCode.NOT_FOUND:
            raise HTTPException(status_code=404, detail="Item not found or unauthorized")
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/seller/items/{item_id}/quantity")
def update_quantity(item_id: int, data: UpdateQuantityModel, x_session_id: str = Header(None)):
    user_id, _ = verify_session(x_session_id)
    try:
        resp = _grpc_call(
            product_stubs,
            "UpdateItemQuantity",
            database_pb2.UpdateItemQuantityRequest(item_id=item_id, seller_id=user_id, quantity_delta=data.quantity_delta),
            timeout=10.0,
        )
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
    resp = _grpc_read_call(
        product_stubs,
        "GetItemsBySeller",
        database_pb2.GetItemsBySellerRequest(seller_id=user_id),
        empty_attr="items",
    )
    return {
        "items": [
            {
                "item_id": item.item_id,
                "item_name": item.item_name,
                "category": item.category,
                "keywords": list(item.keywords),
                "condition_is_new": item.condition_is_new,
                "price": item.price,
                "quantity": item.quantity,
            }
            for item in resp.items
        ]
    }


@app.get("/seller/items/{item_id}")
def get_item(item_id: int, x_session_id: str = Header(None)):
    user_id, _ = verify_session(x_session_id)
    try:
        item = _grpc_read_call(product_stubs, "GetItem", database_pb2.GetItemRequest(item_id=item_id))
    except grpc.RpcError as e:
        if e.code() == grpc.StatusCode.NOT_FOUND:
            raise HTTPException(status_code=404, detail="Item not found")
        raise HTTPException(status_code=500, detail=str(e))
    if item.seller_id != user_id:
        raise HTTPException(status_code=404, detail="Item not found or unauthorized")
    return {
        "item_id": item.item_id,
        "item_name": item.item_name,
        "category": item.category,
        "keywords": list(item.keywords),
        "condition_is_new": item.condition_is_new,
        "price": item.price,
        "quantity": item.quantity,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
