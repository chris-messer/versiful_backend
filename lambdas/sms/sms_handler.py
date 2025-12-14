import json
import logging
import base64
try:
    from helpers import generate_photo, send_message, generate_response, parse_url_string
except:
    from lambdas.sms.helpers import generate_photo, send_message, generate_response, parse_url_string
from twilio.twiml.messaging_response import MessagingResponse
from twilio.rest import Client

# from helpers import generate_response

import sys

logger = logging.getLogger()
logger.setLevel(logging.INFO)



if not logger.handlers:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
    logger.addHandler(handler)

def handler(event, context):
    logger.info('Received event: %s', event)
    if event.get("isBase64Encoded", False):
        params = parse_url_string(base64.b64decode(event["body"]))
        params = {key.decode('utf-8'): value.decode('utf-8') for key, value in params.items()}
    else:
        params = parse_url_string(event['body'])


    body = params.get('Body', None)
    from_num = params.get('From', None)

    logger.info('Message body retrieved: %s', body)

    resp = MessagingResponse()

    if body is not None:
        logger.info('Message body found!')
        try:
            logger.info('Fetching from GPT')
            gpt_response = generate_response(body)
            if 'error' in gpt_response:
                E = gpt_response['error']['message']
                logger.info('GPT Error: %s', E)
            else:
                logger.info('Sending Message...')
                send_message(from_num, gpt_response)
                return {
                    "statusCode": 200,
                    "headers": {
                        "Access-Control-Allow-Origin": "*",
                        "Access-Control-Allow-Methods": "OPTIONS,POST",
                        "Access-Control-Allow-Headers": "Content-Type,Authorization"
                    },
                    # "body": json.dumps({
                    #     "parable": f"{gpt_response}",
                    # })
                }

            # resp.message(f"Posting \n Prompt: {prompt}\n Status: {status}")
            # return str(resp)

        except Exception as E:
            logger.info('Error: %s', E)
            return {
                "statusCode": 500,
                "headers": {
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Allow-Methods": "OPTIONS,POST",
                    "Access-Control-Allow-Headers": "Content-Type,Authorization"
                },
                "body": json.dumps({"error": str(E)})
            }

    else:
        logger.info('Body was none, exiting')
        # Return 200 for OPTIONS/health checks
        return {
            "statusCode": 200,
            "headers": {
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "OPTIONS,POST",
                "Access-Control-Allow-Headers": "Content-Type,Authorization"
            },
            "body": json.dumps({"message": "OK"})
        }

