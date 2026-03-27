from __future__ import annotations

import sys
from pathlib import Path

import grpc

REPO_ROOT = Path(__file__).resolve().parents[1]
GENERATED_ROOT = REPO_ROOT / "generated"
if str(GENERATED_ROOT) not in sys.path:
    sys.path.insert(0, str(GENERATED_ROOT))

from protos import database_pb2, database_pb2_grpc  # noqa: E402


class CustomerDbClient:
    def __init__(self, host: str = "127.0.0.1", port: int = 55061):
        self.target = f"{host}:{port}"
        self.channel = grpc.insecure_channel(self.target)
        self.stub = database_pb2_grpc.DatabaseServiceStub(self.channel)

    def close(self) -> None:
        self.channel.close()

    def create_buyer(self, username: str, password: str) -> int:
        resp = self.stub.CreateAccount(
            database_pb2.CreateAccountRequest(role="buyer", username=username, password=password)
        )
        return resp.user_id

    def create_seller(self, username: str, password: str) -> int:
        resp = self.stub.CreateAccount(
            database_pb2.CreateAccountRequest(role="seller", username=username, password=password)
        )
        return resp.user_id

    def login_buyer(self, username: str, password: str) -> tuple[int, str]:
        resp = self.stub.AuthenticateUser(
            database_pb2.AuthenticateRequest(role="buyer", username=username, password=password)
        )
        return resp.user_id, resp.session_id

    def login_seller(self, username: str, password: str) -> tuple[int, str]:
        resp = self.stub.AuthenticateUser(
            database_pb2.AuthenticateRequest(role="seller", username=username, password=password)
        )
        return resp.user_id, resp.session_id

    def verify_session(self, session_id: str) -> tuple[int, str]:
        resp = self.stub.VerifySession(database_pb2.VerifySessionRequest(session_id=session_id))
        return resp.user_id, resp.role

    def logout(self, session_id: str, user_id: int, role: str, scope: str = "single") -> None:
        self.stub.DeleteSessions(
            database_pb2.DeleteSessionsRequest(
                session_id=session_id,
                user_id=user_id,
                role=role,
                scope=scope,
            )
        )

    def get_seller_rating(self, seller_id: int) -> tuple[int, int]:
        resp = self.stub.GetSellerRating(database_pb2.GetSellerRatingRequest(seller_id=seller_id))
        return resp.pos, resp.neg
