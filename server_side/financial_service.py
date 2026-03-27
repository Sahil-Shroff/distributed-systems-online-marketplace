from __future__ import annotations

import os
import random

from spyne import Application, Boolean, ServiceBase, Unicode, rpc
from spyne.protocol.soap import Soap11
from spyne.server.wsgi import WsgiApplication
from wsgiref.simple_server import make_server


class FinancialTransactionsService(ServiceBase):
    @rpc(Unicode, Unicode, Unicode, Unicode, _returns=Boolean)
    def AuthorizePayment(ctx, username: str, credit_card_number: str, expiration_date: str, security_code: str) -> bool:
        # Assignment-required mock behavior: approve about 90% of the time.
        return random.random() < 0.9


soap_app = Application(
    [FinancialTransactionsService],
    tns="marketplace.financial",
    in_protocol=Soap11(validator="lxml"),
    out_protocol=Soap11(),
)

application = WsgiApplication(soap_app)


def serve() -> None:
    host = os.getenv("FINANCIAL_SERVICE_HOST", "0.0.0.0")
    port = int(os.getenv("FINANCIAL_SERVICE_PORT", "8002"))
    server = make_server(host, port, application)
    print(f"Financial SOAP service listening on http://{host}:{port}/")
    server.serve_forever()


if __name__ == "__main__":
    serve()
