import json
import boto3
import os

dynamodb = boto3.resource("dynamodb")
env = os.environ["ENVIRONMENT"]
project_name = os.environ["PROJECT_NAME"]
table_name = f"{env}-{project_name}-users"
table = dynamodb.Table(table_name)


def create_user(body, headers):
    user_id = body.get("userId")
    if not user_id:
        return {"statusCode": 400, "headers": headers, "body": json.dumps({"error": "Missing userId"})}

    response = table.get_item(Key={"userId": user_id})
    if "Item" in response:
        return {"statusCode": 200, "headers": headers, "body": json.dumps({"exists": True})}

    table.put_item(Item={"userId": user_id})
    return {"statusCode": 200, "headers": headers, "body": json.dumps({"exists": False})}


def get_user_profile(body, headers):
    user_id = body.get("userId")
    if not user_id:
        return {"statusCode": 400, "headers": headers, "body": json.dumps({"error": "Missing userId"})}

    response = table.get_item(Key={"userId": user_id})
    if "Item" in response:
        return {"statusCode": 200, "headers": headers, "body": json.dumps(response["Item"])}

    return {"statusCode": 404, "headers": headers, "body": json.dumps({"error": "User not found"})}

# def update_user_settings(body, headers):
#     user_id = body.get("userId")
#     new_settings = body.get("settings")
#
#     if not user_id or not new_settings:
#         return {"statusCode": 400, "headers": headers, "body": json.dumps({"error": "Missing parameters"})}
#
#     table.update_item(
#         Key={"userId": user_id},
#         UpdateExpression="set settings = :s",
#         ExpressionAttributeValues={":s": new_settings}
#     )
#
#     return {"statusCode": 200, "headers": headers, "body": json.dumps({"message": "Settings updated"})}
