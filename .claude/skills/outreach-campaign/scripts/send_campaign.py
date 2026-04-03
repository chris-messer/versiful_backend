#!/usr/bin/env python3
"""
Send outreach SMS messages and log them to chat-messages table.

Usage:
    python .claude/skills/outreach-campaign/scripts/send_campaign.py <csv_file>

Example:
    python send_campaign.py outreach_messages.csv

CSV Format:
    phone_number,first_name,engagement_level,message
    +18005551234,John,2,"Hi John, it's Versiful!..."

Environment:
    Requires SECRET_ARN environment variable to be set for Twilio access
"""

import boto3
import csv
import sys
import os
from uuid import uuid4
from datetime import datetime, timezone
import time

# Add parent directory to path for imports
script_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.abspath(os.path.join(script_dir, '..', '..', '..'))
sys.path.append(os.path.join(backend_dir, 'lambdas', 'shared'))

from sms_notifications import send_sms, VERSIFUL_PHONE

# DynamoDB setup
dynamodb = boto3.resource('dynamodb')
messages_table = dynamodb.Table('prod-versiful-chat-messages')
users_table = dynamodb.Table('prod-versiful-users')


def get_user_id_by_phone(phone_number: str) -> str:
    """
    Look up userId by phone number in users table.

    Args:
        phone_number: Phone number to look up

    Returns:
        userId if found, None otherwise
    """
    try:
        response = users_table.scan(
            FilterExpression='phoneNumber = :phone',
            ExpressionAttributeValues={':phone': phone_number}
        )

        if response.get('Items'):
            return response['Items'][0].get('userId')
    except Exception as e:
        print(f"  Warning: Error looking up userId: {str(e)}")

    return None


def log_outbound_message(phone_number: str, message: str, user_id: str = None):
    """
    Log an outbound SMS message to the chat-messages table.

    Args:
        phone_number: Recipient phone number (E.164 format)
        message: Message content
        user_id: Optional user ID if known
    """
    timestamp = datetime.now(timezone.utc).isoformat()

    # For SMS, threadId is the phone number
    thread_id = phone_number

    message_item = {
        'threadId': thread_id,
        'timestamp': timestamp,
        'messageId': str(uuid4()),
        'role': 'assistant',  # Outbound messages are from assistant
        'content': message,
        'channel': 'sms',
        'createdAt': timestamp,
        'updatedAt': timestamp,
        'phoneNumber': phone_number
    }

    if user_id:
        message_item['userId'] = user_id

    try:
        messages_table.put_item(Item=message_item)
        print(f"  ✓ Logged message to chat-messages table")
        return True
    except Exception as e:
        print(f"  ✗ Error logging message: {str(e)}")
        return False


def send_outreach_campaign(csv_file: str):
    """
    Send all outreach messages from CSV and log to DynamoDB.

    Args:
        csv_file: Path to CSV file with campaign data
    """
    if not os.path.exists(csv_file):
        print(f"Error: {csv_file} not found")
        return

    # Count rows
    with open(csv_file, 'r') as f:
        row_count = sum(1 for _ in csv.DictReader(f))

    print(f"Versiful Outreach Campaign")
    print(f"=" * 80)
    print(f"Sending from: {VERSIFUL_PHONE}")
    print(f"Reading from: {csv_file}")
    print(f"Total recipients: {row_count}")
    print(f"=" * 80)
    print()

    sent_count = 0
    failed_count = 0

    with open(csv_file, 'r') as f:
        reader = csv.DictReader(f)

        for i, row in enumerate(reader, 1):
            phone_number = row['phone_number']
            first_name = row.get('first_name', '')
            message = row['message']

            name_display = first_name if first_name else phone_number

            print(f"{i}. {name_display} ({phone_number})")
            print(f"   Message: {message[:60]}...")

            # Send SMS
            message_sid = send_sms(phone_number, message)

            if message_sid:
                print(f"  ✓ SMS sent successfully (SID: {message_sid})")

                # Look up userId by phone number
                user_id = get_user_id_by_phone(phone_number)

                # Log to chat-messages table
                log_success = log_outbound_message(phone_number, message, user_id)

                if log_success:
                    sent_count += 1
                else:
                    failed_count += 1
            else:
                print(f"  ✗ Failed to send SMS")
                failed_count += 1

            print()

            # Rate limiting: Wait 1 second between messages to avoid carrier throttling
            if i < row_count:
                time.sleep(1)

    print("=" * 80)
    print(f"Campaign Summary:")
    print(f"  Sent successfully: {sent_count}")
    print(f"  Failed: {failed_count}")
    print(f"  Total: {sent_count + failed_count}")
    print("=" * 80)


def main():
    if len(sys.argv) != 2:
        print("Usage: python send_campaign.py <csv_file>")
        print("Example: python send_campaign.py outreach_messages.csv")
        sys.exit(1)

    csv_file = sys.argv[1]

    # Count recipients
    with open(csv_file, 'r') as f:
        count = sum(1 for _ in csv.DictReader(f))

    print()
    response = input(f"⚠️  You are about to send SMS messages to {count} users. Continue? (yes/no): ")

    if response.lower() != 'yes':
        print("Aborted.")
        sys.exit(0)

    print()
    send_outreach_campaign(csv_file)


if __name__ == "__main__":
    main()
