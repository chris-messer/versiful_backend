import json
import os
import re
import sys
from typing import Optional
from datetime import datetime, timezone
from decimal import Decimal

import boto3
from boto3.dynamodb.conditions import Attr

# Add Lambda layer path for shared code
sys.path.append('/opt/python')

# Import SMS notifications helper
try:
    from sms_notifications import send_welcome_sms
except ImportError:
    # Fallback for local testing
    from lambdas.shared.sms_notifications import send_welcome_sms

# Custom JSON encoder to handle Decimal objects from DynamoDB
class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            # Convert Decimal to int if it has no decimal places, otherwise to float
            if obj % 1 == 0:
                return int(obj)
            else:
                return float(obj)
        return super(DecimalEncoder, self).default(obj)

dynamodb = boto3.resource("dynamodb")
env = os.environ["ENVIRONMENT"]
project_name = os.environ["PROJECT_NAME"]
table_name = f"{env}-{project_name}-users"
sms_usage_table_name = os.environ.get("SMS_USAGE_TABLE", f"{env}-{project_name}-sms-usage")
table = dynamodb.Table(table_name)
sms_usage_table = dynamodb.Table(sms_usage_table_name)


def normalize_phone_number(raw: str) -> Optional[str]:
    """Normalize to E.164 (+1########## for US defaults). Return None if invalid."""
    if not raw:
        return None
    digits = re.sub(r"[^\d+]", "", raw)
    if digits.startswith("+"):
        digits_only = re.sub(r"[^\d]", "", digits)
        if 10 <= len(digits_only) <= 15:
            return f"+{digits_only}"
        return None
    digits_only = re.sub(r"[^\d]", "", raw)
    if len(digits_only) == 10:
        return f"+1{digits_only}"
    if len(digits_only) == 11 and digits_only.startswith("1"):
        return f"+{digits_only}"
    return None


def ensure_sms_usage_record(phone_number: str, user_id: str):
    """Create or update sms-usage record with userId for the phone."""
    now = datetime.now(timezone.utc).isoformat()
    sms_usage_table.update_item(
        Key={"phoneNumber": phone_number},
        UpdateExpression=(
            "SET userId = if_not_exists(userId, :userId), "
            "updatedAt = :now"
        ),
        ExpressionAttributeValues={
            ":userId": user_id,
            ":now": now,
        },
    )


def create_user(event, headers):
    try:
        user_id = event["requestContext"]["authorizer"]["userId"]
    except (KeyError, TypeError):
        return {"statusCode": 401, "body": json.dumps({"error": "Unauthorized - Missing userId"})}
    
    if not user_id:
        return {"statusCode": 400, "body": json.dumps({"error": "Missing userId"})}

    response = table.get_item(Key={"userId": user_id})
    if "Item" in response:
        subscribed = response["Item"].get("isSubscribed", False)
        registered = response["Item"].get("isRegistered", False)
        return {"statusCode": 200,"body": json.dumps({"isSubscribed": subscribed, "isRegistered": registered}, cls=DecimalEncoder)}

    table.put_item(Item={"userId": user_id})
    return {"statusCode": 200, "body": json.dumps({"isSubscribed": False, "isRegistered": False})}


def get_user_profile(event, headers):
    try:
        user_id = event["requestContext"]["authorizer"]["userId"]
    except (KeyError, TypeError):
        return {"statusCode": 401, "headers": headers, "body": json.dumps({"error": "Unauthorized - Missing userId"})}
    
    if not user_id:
        return {"statusCode": 400, "headers": headers, "body": json.dumps({"error": "Missing userId"})}

    response = table.get_item(Key={"userId": user_id})
    if "Item" in response:
        user_data = response["Item"]
        
        # Fetch SMS usage data if user has a phone number
        phone_number = user_data.get("phoneNumber")
        if phone_number:
            try:
                usage_response = sms_usage_table.get_item(Key={"phoneNumber": phone_number})
                if "Item" in usage_response:
                    usage_data = usage_response["Item"]
                    # Add usage info to user profile
                    user_data["smsUsage"] = {
                        "messagesSent": int(usage_data.get("plan_messages_sent", 0)),
                        "periodKey": usage_data.get("periodKey"),
                        "messageLimit": 5 if not user_data.get("isSubscribed") else None  # None = unlimited
                    }
            except Exception as e:
                # Log but don't fail - usage data is optional
                print(f"Failed to fetch SMS usage for {phone_number}: {str(e)}")
        
        return {"statusCode": 200, "headers": headers, "body": json.dumps(user_data, cls=DecimalEncoder)}

    return {"statusCode": 404, "headers": headers, "body": json.dumps({"error": "User not found"})}

def update_user_settings(event, headers):
    try:
        try:
            user_id = event["requestContext"]["authorizer"]["userId"]
        except (KeyError, TypeError):
            return {"statusCode": 401, "body": json.dumps({"error": "Unauthorized - Missing userId"})}
        
        body = json.loads(event["body"])

        # Ensure the user item exists before attempting an update
        existing = table.get_item(Key={"userId": user_id})
        if "Item" not in existing:
            table.put_item(Item={"userId": user_id})

        update_expression = "SET "
        expression_attribute_values = {}
        expression_attribute_names = {}
        update_fields = []

        for key, value in body.items():
            if value is None:
                continue  # Ignore null values

            if key == "phoneNumber":
                normalized = normalize_phone_number(value)
                if not normalized:
                    return {
                        "statusCode": 400,
                        "body": json.dumps({"message": "Invalid phone number"})
                    }
                value = normalized
                ensure_sms_usage_record(value, user_id)

            update_fields.append(f"#{key} = :{key}")
            expression_attribute_values[f":{key}"] = value
            expression_attribute_names[f"#{key}"] = key

        if not update_fields:
            return {
                "statusCode": 400,
                "body": json.dumps({"message": "No valid fields to update"})
            }

        update_expression += ", ".join(update_fields)

        # Perform update in DynamoDB
        table.update_item(
            Key={"userId": user_id},
            UpdateExpression=update_expression,
            ExpressionAttributeNames=expression_attribute_names,
            ExpressionAttributeValues=expression_attribute_values,
            ReturnValues="UPDATED_NEW"
        )

        # Send welcome SMS if this is a new registration (isRegistered=true with a phone number)
        is_new_registration = expression_attribute_values.get(":isRegistered") is True
        phone_number = expression_attribute_values.get(":phoneNumber")
        
        if is_new_registration and phone_number:
            first_name = expression_attribute_values.get(":firstName")
            try:
                send_welcome_sms(phone_number, first_name)
            except Exception as sms_error:
                # Log error but don't fail the request
                print(f"Failed to send welcome SMS to {phone_number}: {str(sms_error)}")

        return {"statusCode": 200, "body": json.dumps({"message": "Settings updated"})}

    except Exception as e:
        return {
            "statusCode": 500,
            "body": json.dumps({"error": str(e)})
        }