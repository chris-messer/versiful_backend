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

    path = event.get("path", "")
    method = event.get("httpMethod", "")


    try:

        if method == "GET":
            if path.endswith("/users"):
                return get_user_profile(event, {})
        if method == "POST":
            if path.endswith("/users"):
                r = create_user(event, {})
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
                "body": json.dumps({"error": "Invalid route"})
            }
    except Exception as e:
        return {
            "statusCode": 500,
            "body": json.dumps({"error": str(e)})
        }
