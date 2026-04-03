#!/usr/bin/env python3
"""
Generate CSV from analysis plan for campaign execution.

This is a helper script to convert analyzed user data into a CSV format
for review before executing the campaign.

Usage:
    # For registered users
    python generate_csv.py --segment registered --output outreach_messages.csv

    # For unregistered texters
    python generate_csv.py --segment unregistered --output unregistered_outreach.csv
"""

import argparse
import boto3
import csv
from datetime import datetime
from boto3.dynamodb.conditions import Attr

dynamodb = boto3.resource('dynamodb')
users_table = dynamodb.Table('prod-versiful-users')
messages_table = dynamodb.Table('prod-versiful-chat-messages')
sms_usage_table = dynamodb.Table('prod-versiful-sms-usage')


def get_user_message_count(user_id: str, phone_number: str = None) -> int:
    """Get count of user messages."""
    # Try by userId
    try:
        response = messages_table.query(
            KeyConditionExpression='threadId = :tid',
            FilterExpression='#role = :user_role',
            ExpressionAttributeNames={'#role': 'role'},
            ExpressionAttributeValues={
                ':tid': user_id,
                ':user_role': 'user'
            }
        )
        if response['Items']:
            return len(response['Items'])
    except:
        pass

    # Try by phone
    if phone_number:
        try:
            response = messages_table.query(
                KeyConditionExpression='threadId = :tid',
                FilterExpression='#role = :user_role',
                ExpressionAttributeNames={'#role': 'role'},
                ExpressionAttributeValues={
                    ':tid': phone_number,
                    ':user_role': 'user'
                }
            )
            return len(response['Items'])
        except:
            pass

    return 0


def generate_message(first_name: str, engagement_level: int) -> str:
    """Generate personalized message based on name and engagement."""
    greeting = f"Hi {first_name}" if first_name else "Hi"

    if engagement_level >= 3:
        message = (
            f"{greeting}, it's Versiful! We noticed you've been asking questions but haven't registered yet.\\n\\n"
            "Create a free account at https://versiful.io to:\\n"
            "• Get personalized biblical guidance\\n"
            "• Choose your preferred Bible version\\n\\n"
            "What's on your heart today?"
        )
    elif engagement_level == 2:
        message = (
            f"{greeting}, it's Versiful! It's been a while since we last connected. "
            "We're here to provide biblical guidance anytime you need it.\\n\\n"
            "Register at https://versiful.io for free to get personalized responses.\\n\\n"
            "What can we help you with today?"
        )
    else:
        message = (
            f"{greeting}! It's Versiful. It's been a while since we last connected. "
            "We're here to provide biblical guidance whenever you need it.\\n\\n"
            "Create a free account at https://versiful.io to:\\n"
            "• Personalized biblical guidance\\n"
            "• Your preferred Bible version\\n\\n"
            "Reply anytime with questions!"
        )

    return message


def generate_registered_csv(output_file: str):
    """Generate CSV for registered non-subscribers."""
    response = users_table.scan(
        FilterExpression=Attr('isRegistered').eq(True) &
                         Attr('isSubscribed').eq(False) &
                         (Attr('skipMarketing').not_exists() | Attr('skipMarketing').eq(False))
    )

    users = response['Items']

    # Filter out same-day signups
    users = [u for u in users if u.get('createdAt') and
             (datetime.now(datetime.fromisoformat(u['createdAt'].replace('Z', '+00:00')).tzinfo) -
              datetime.fromisoformat(u['createdAt'].replace('Z', '+00:00'))).days > 0]

    with open(output_file, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=['phone_number', 'first_name', 'engagement_level', 'message'])
        writer.writeheader()

        for user in users:
            phone = user.get('phoneNumber', '')
            if not phone:
                continue

            first_name = user.get('firstName', '')
            user_id = user.get('userId')

            engagement = get_user_message_count(user_id, phone)
            message = generate_message(first_name, engagement)

            writer.writerow({
                'phone_number': phone,
                'first_name': first_name,
                'engagement_level': engagement,
                'message': message
            })

    print(f"✓ Generated {output_file} with {len(users)} users")


def is_registered(phone_number: str) -> bool:
    """Check if phone number is registered."""
    try:
        response = users_table.scan(
            FilterExpression='phoneNumber = :phone',
            ExpressionAttributeValues={':phone': phone_number}
        )
        return len(response.get('Items', [])) > 0
    except:
        return False


def get_name_from_messages(phone_number: str) -> str:
    """Try to extract name from message history."""
    try:
        response = messages_table.query(
            KeyConditionExpression='threadId = :tid',
            ExpressionAttributeValues={':tid': phone_number},
            ScanIndexForward=True
        )

        messages = response.get('Items', [])
        for msg in messages:
            if msg.get('role') == 'user':
                content = msg.get('content', '').lower()
                if "i'm " in content or "my name is " in content:
                    parts = content.replace("i'm", "my name is").split("my name is")
                    if len(parts) > 1:
                        name_part = parts[1].strip().split()[0]
                        return name_part.capitalize()
    except:
        pass
    return ""


def generate_unregistered_csv(output_file: str):
    """Generate CSV for unregistered texters."""
    sms_response = sms_usage_table.scan()
    sms_usage = sms_response.get('Items', [])

    # Filter to unregistered
    unregistered = []
    for item in sms_usage:
        phone = item.get('phoneNumber')
        if phone and not is_registered(phone):
            # Get message count and check if same-day
            try:
                msg_response = messages_table.query(
                    KeyConditionExpression='threadId = :tid',
                    ExpressionAttributeValues={':tid': phone},
                    ScanIndexForward=False,
                    Limit=1
                )

                if msg_response['Items']:
                    last_msg = msg_response['Items'][0]
                    last_timestamp = last_msg.get('timestamp', '')
                    if last_timestamp:
                        last_date = datetime.fromisoformat(last_timestamp.replace('Z', '+00:00'))
                        days_ago = (datetime.now(last_date.tzinfo) - last_date).days
                        if days_ago == 0:
                            continue  # Skip same-day

                # Get full message count
                full_response = messages_table.query(
                    KeyConditionExpression='threadId = :tid',
                    FilterExpression='#role = :user_role',
                    ExpressionAttributeNames={'#role': 'role'},
                    ExpressionAttributeValues={
                        ':tid': phone,
                        ':user_role': 'user'
                    }
                )

                engagement = len(full_response.get('Items', []))
                first_name = get_name_from_messages(phone)

                unregistered.append({
                    'phone': phone,
                    'first_name': first_name,
                    'engagement': engagement
                })

            except:
                pass

    with open(output_file, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=['phone_number', 'first_name', 'engagement_level', 'message'])
        writer.writeheader()

        for item in unregistered:
            message = generate_message(item['first_name'], item['engagement'])

            writer.writerow({
                'phone_number': item['phone'],
                'first_name': item['first_name'],
                'engagement_level': item['engagement'],
                'message': message
            })

    print(f"✓ Generated {output_file} with {len(unregistered)} users")


def main():
    parser = argparse.ArgumentParser(description='Generate outreach campaign CSV')
    parser.add_argument('--segment', choices=['registered', 'unregistered'],
                        required=True, help='User segment to target')
    parser.add_argument('--output', required=True, help='Output CSV file path')

    args = parser.parse_args()

    if args.segment == 'registered':
        generate_registered_csv(args.output)
    else:
        generate_unregistered_csv(args.output)


if __name__ == "__main__":
    main()
