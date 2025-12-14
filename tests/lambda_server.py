# local_server.py
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from backend.lambdas.sms.sms_handler import handler

class LambdaRequestHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        # Read and parse the JSON body
        content_length = int(self.headers['Content-Length'])
        body = self.rfile.read(content_length)
        try:
            event = json.loads(body)
        except json.JSONDecodeError:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b'Invalid JSON')
            return

        # Optional: Mock context object if needed
        context = {}

        # Call the Lambda function
        response = handler(event, context)

        # Send response
        self.send_response(response.get("statusCode", 200))
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(response.get("body")).encode())

def run(server_class=HTTPServer, handler_class=LambdaRequestHandler, port=9000):
    server_address = ('', port)
    httpd = server_class(server_address, handler_class)
    print(f'Starting local Lambda server on port {port}...')
    httpd.serve_forever()

if __name__ == '__main__':
    run()