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
    user_id = event["requestContext"]["authorizer"]["userId"]
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
    user_id = event["requestContext"]["authorizer"]["userId"]
    if not user_id:
        return {"statusCode": 400, "headers": headers, "body": json.dumps({"error": "Missing userId"})}

    response = table.get_item(Key={"userId": user_id})
    if "Item" in response:
        return {"statusCode": 200, "headers": headers, "body": json.dumps(response["Item"], cls=DecimalEncoder)}

    return {"statusCode": 404, "headers": headers, "body": json.dumps({"error": "User not found"})}

def update_user_settings(event, headers):
    try:
        user_id = event["requestContext"]["authorizer"]["userId"]
        body = json.loads(event["body"])

        # Ensure the user item exists before attempting an update
        existing = table.get_item(Key={"userId": user_id})
        if "Item" not in existing:
            table.put_item(Item={"userId": user_id})

        # Track if this is the first time a phone number is being registered
        is_new_phone_registration = False
        existing_phone = existing.get("Item", {}).get("phoneNumber") if "Item" in existing else None

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
                
                # Check if this is a new phone registration (not an update)
                if not existing_phone:
                    is_new_phone_registration = True

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

        # Send welcome SMS if this is a new phone registration
        if is_new_phone_registration:
            phone_number = expression_attribute_values.get(":phoneNumber")
            first_name = expression_attribute_values.get(":firstName")
            if phone_number:
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