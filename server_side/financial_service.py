import random
from spyne import Application, rpc, ServiceBase, Unicode, Boolean
from spyne.protocol.soap import Soap11
from spyne.server.wsgi import WsgiApplication
from wsgiref.simple_server import make_server

class FinancialTransactionService(ServiceBase):
    @rpc(Unicode, Unicode, Unicode, Unicode, _returns=Boolean)
    def AuthorizePayment(self, username, card_number, expiration_date, security_code):
        print(f"Auth request for {username} (Card: {card_number})")
        # 90% probability of Success
        return random.random() < 0.9

application = Application(
    [FinancialTransactionService],
    tns='marketplace.financial.soap',
    in_protocol=Soap11(validator='lxml'),
    out_protocol=Soap11()
)

if __name__ == '__main__':
    wsgi_app = WsgiApplication(application)
    server = make_server('0.0.0.0', 8002, wsgi_app)
    print("SOAP Financial Service starting on port 8002...")
    print("WSDL is available at: http://localhost:8002/?wsdl")
    server.serve_forever()
