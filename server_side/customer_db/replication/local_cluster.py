from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

import grpc
import psycopg2

from server_side.customer_db.tests.postgres_support import CUSTOMER_SCHEMA_DDL, postgres_dsn


REPO_ROOT = Path(__file__).resolve().parents[3]


def _wait_for_port(host: str, port: int, timeout_seconds: float) -> None:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.2)
            try:
                sock.connect((host, port))
                return
            except OSError:
                time.sleep(0.1)
    raise TimeoutError(f"Timed out waiting for {host}:{port}")


@dataclass(frozen=True)
class ReplicaProcess:
    replica_id: int
    grpc_host: str
    grpc_port: int
    udp_host: str
    udp_port: int
    schema: str
    process: subprocess.Popen[str]

    @property
    def grpc_target(self) -> str:
        return f"{self.grpc_host}:{self.grpc_port}"


class LocalCustomerDbReplicaCluster:
    def __init__(
        self,
        replica_count: int = 3,
        grpc_base_port: int = 50061,
        udp_base_port: int = 51061,
        host: str = "127.0.0.1",
        database_prefix: str | None = None,
    ):
        self.replica_count = replica_count
        self.grpc_base_port = grpc_base_port
        self.udp_base_port = udp_base_port
        self.host = host
        self.database_prefix = database_prefix
        self.schemas: list[str] = []
        self.database_names: list[str] = []
        self.replicas: list[ReplicaProcess] = []

    def start(self, startup_timeout_seconds: float = 10.0) -> None:
        self._create_schemas()
        peer_spec = ",".join(
            f"{replica_id}:{self.host}:{self.udp_base_port + replica_id}"
            for replica_id in range(self.replica_count)
        )
        for replica_id in range(self.replica_count):
            schema = self.schemas[replica_id] if self.schemas else ""
            env = os.environ.copy()
            env.update(
                {
                    "DB_SERVICE_BIND": f"{self.host}:{self.grpc_base_port + replica_id}",
                    "DB_SERVICE_PORT": str(self.grpc_base_port + replica_id),
                    "CUSTOMER_DB_REPLICA_ID": str(replica_id),
                    "CUSTOMER_DB_REPLICA_PEERS": peer_spec,
                    "CUSTOMER_DB_REPLICATION_BIND_HOST": self.host,
                    "CUSTOMER_DB_REPLICATION_BIND_PORT": str(self.udp_base_port + replica_id),
                }
            )
            if self.database_names:
                env["CUSTOMER_DB_NAME"] = self.database_names[replica_id]
                env.pop("CUSTOMER_PGOPTIONS", None)
            else:
                env["CUSTOMER_PGOPTIONS"] = f"-c search_path={schema}"
            process = subprocess.Popen(
                [sys.executable, "server_side/db_service.py"],
                cwd=str(REPO_ROOT),
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
            self.replicas.append(
                ReplicaProcess(
                    replica_id=replica_id,
                    grpc_host=self.host,
                    grpc_port=self.grpc_base_port + replica_id,
                    udp_host=self.host,
                    udp_port=self.udp_base_port + replica_id,
                    schema=schema,
                    process=process,
                )
            )
        try:
            for replica in self.replicas:
                _wait_for_port(replica.grpc_host, replica.grpc_port, startup_timeout_seconds)
        except Exception:
            self.stop()
            raise

    def stop(self) -> None:
        for replica in self.replicas:
            if replica.process.poll() is None:
                replica.process.terminate()
        for replica in self.replicas:
            if replica.process.poll() is None:
                try:
                    replica.process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    replica.process.kill()
            if replica.process.stdout is not None:
                try:
                    replica.process.stdout.close()
                except Exception:
                    pass
        self.replicas.clear()
        self._drop_schemas()

    def wait_for_grpc_ready(self, timeout_seconds: float = 10.0) -> None:
        deadline = time.time() + timeout_seconds
        for replica in self.replicas:
            channel = grpc.insecure_channel(replica.grpc_target)
            try:
                remaining = max(deadline - time.time(), 0.1)
                grpc.channel_ready_future(channel).result(timeout=remaining)
            finally:
                channel.close()

    def read_process_output(self) -> dict[int, str]:
        outputs: dict[int, str] = {}
        for replica in self.replicas:
            if replica.process.stdout is None:
                outputs[replica.replica_id] = ""
                continue
            try:
                outputs[replica.replica_id] = replica.process.stdout.read() or ""
            except Exception:
                outputs[replica.replica_id] = ""
        return outputs

    def _create_schemas(self) -> None:
        if self.database_prefix:
            self.database_names = [f"{self.database_prefix}{idx}" for idx in range(self.replica_count)]
            return
        root_conn = psycopg2.connect(**postgres_dsn())
        try:
            with root_conn, root_conn.cursor() as cur:
                for _ in range(self.replica_count):
                    schema = f"customer_udp_{uuid.uuid4().hex[:8]}"
                    self.schemas.append(schema)
                    cur.execute(f"CREATE SCHEMA {schema}")
                    cur.execute(f"SET search_path TO {schema}")
                    cur.execute(CUSTOMER_SCHEMA_DDL)
        finally:
            root_conn.close()

    def _drop_schemas(self) -> None:
        if self.database_names:
            self.database_names.clear()
            return
        if not self.schemas:
            return
        root_conn = psycopg2.connect(**postgres_dsn())
        try:
            with root_conn, root_conn.cursor() as cur:
                for schema in self.schemas:
                    cur.execute(f"DROP SCHEMA IF EXISTS {schema} CASCADE")
        finally:
            root_conn.close()
        self.schemas.clear()
