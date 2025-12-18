import json
import boto3
import os
from boto3.dynamodb.conditions import Attr

dynamodb = boto3.resource("dynamodb")
env = os.environ["ENVIRONMENT"]
project_name = os.environ["PROJECT_NAME"]
table_name = f"{env}-{project_name}-users"
table = dynamodb.Table(table_name)


def create_user(event, headers):
    user_id = event["requestContext"]["authorizer"]["userId"]
    if not user_id:
        return {"statusCode": 400, "body": json.dumps({"error": "Missing userId"})}

    response = table.get_item(Key={"userId": user_id})
    if "Item" in response:
        subscribed = response["Item"].get("isSubscribed", False)
        registered = response["Item"].get("isRegistered", False)
        return {"statusCode": 200,"body": json.dumps({"isSubscribed": subscribed, "isRegistered": registered})}

    table.put_item(Item={"userId": user_id})
    return {"statusCode": 200, "body": json.dumps({"isSubscribed": False, "isRegistered": False})}


def get_user_profile(event, headers):
    user_id = event["requestContext"]["authorizer"]["userId"]
    if not user_id:
        return {"statusCode": 400, "headers": headers, "body": json.dumps({"error": "Missing userId"})}

    response = table.get_item(Key={"userId": user_id})
    if "Item" in response:
        return {"statusCode": 200, "headers": headers, "body": json.dumps(response["Item"])}

    return {"statusCode": 404, "headers": headers, "body": json.dumps({"error": "User not found"})}

def update_user_settings(event, headers):
    try:
        user_id = event["requestContext"]["authorizer"]["userId"]
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
            if value is not None:  # Ignore null values
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

        return {"statusCode": 200, "body": json.dumps({"message": "Settings updated"})}

    except Exception as e:
        return {
            "statusCode": 500,
            "body": json.dumps({"error": str(e)})
        }