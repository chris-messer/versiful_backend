import json
import os

def handler(event, context):
    """Handle CORS preflight OPTIONS requests."""
    # Get allowed origins from environment or use default
    allowed_origins = os.environ.get("ALLOWED_CORS_ORIGINS", "*")
    
    # Get origin from request
    origin = event.get("headers", {}).get("origin", "*")
    
    # If specific origins are configured, validate the origin
    if allowed_origins != "*":
        origins_list = allowed_origins.split(",")
        if origin not in origins_list:
            origin = origins_list[0]  # Default to first allowed origin
    
    return {
        "statusCode": 200,
        "headers": {
            "Access-Control-Allow-Origin": origin,
            "Access-Control-Allow-Methods": "OPTIONS,GET,POST,PUT,DELETE",
            "Access-Control-Allow-Headers": "Content-Type,Authorization,X-Amz-Date,X-Api-Key,X-Amz-Security-Token",
            "Access-Control-Allow-Credentials": "true",
            "Access-Control-Max-Age": "86400"
        },
        "body": json.dumps({"message": "CORS preflight OK"})
    }