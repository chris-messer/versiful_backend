import json

try:
    from helpers import *
except:
    from lambdas.users.helpers import *

import logging
import sys

logger = logging.getLogger()
logger.setLevel(logging.INFO)



if not logger.handlers:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
    logger.addHandler(handler)

def handler(event, context):
    headers = {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "OPTIONS, GET, POST, PUT, DELETE",
        "Access-Control-Allow-Headers": "Content-Type, Authorization"
    }
    logger.info('Received event: %s', event)
    # Handle CORS preflight requests
    if event["httpMethod"] == "OPTIONS":
        return {
            "statusCode": 200,
            "headers": headers,
            "body": json.dumps({})
        }

    path = event.get("path", "")
    method = event.get("httpMethod", "")
    body = json.loads(event.get("body", "{}"))

    try:

        if method == "GET":
            if path.endswith("/users"):
                return get_user_profile(body, headers)
        if method == "POST":
            if path.endswith("/users"):
                r = create_user(body, headers)
                logger.info('Response: %s', event)
                return r

        #
        # if path.endswith("/users") and method == "POST":
        #     return create_user(body, headers)
        # elif path.endswith("/user/profile") and method == "GET":
        #     return get_user_profile(body, headers)
        # elif path.endswith("/user/settings") and method == "POST":
        #     return update_user_settings(body, headers)
        else:
            return {
                "statusCode": 404,
                "headers": headers,
                "body": json.dumps({"error": "Invalid route"})
            }
    except Exception as e:
        return {
            "statusCode": 500,
            "headers": headers,
            "body": json.dumps({"error": str(e)})
        }
