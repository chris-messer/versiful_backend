#!/usr/bin/env python3
"""
Analyze registered users who haven't subscribed and generate outreach plan.

Usage:
    python .claude/skills/outreach-campaign/scripts/analyze_registered_users.py

Output:
    - Prints markdown analysis to stdout
    - Use > to redirect to file: python script.py > user_outreach_plan.md
"""

import boto3
from datetime import datetime
from boto3.dynamodb.conditions import Attr

dynamodb = boto3.resource('dynamodb')
users_table = dynamodb.Table('prod-versiful-users')
messages_table = dynamodb.Table('prod-versiful-chat-messages')


def get_user_message_history(user_id: str, phone_number: str = None):
    """Get message history for a user by userId or phone number."""
    # Try by userId first (web chat)
    try:
        response = messages_table.query(
            KeyConditionExpression='threadId = :tid',
            ExpressionAttributeValues={':tid': user_id},
            ScanIndexForward=True
        )
        if response['Items']:
            return response['Items']
    except:
        pass

    # Try by phone number (SMS)
    if phone_number:
        try:
            response = messages_table.query(
                KeyConditionExpression='threadId = :tid',
                ExpressionAttributeValues={':tid': phone_number},
                ScanIndexForward=True
            )
            return response['Items']
        except:
            pass

    return []


def calculate_days_ago(timestamp_str: str) -> int:
    """Calculate days since timestamp."""
    try:
        timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
        return (datetime.now(timestamp.tzinfo) - timestamp).days
    except:
        return -1


def generate_message(first_name: str, engagement_level: int) -> str:
    """Generate personalized message based on name and engagement."""
    greeting = f"Hi {first_name}" if first_name else "Hi"

    if engagement_level >= 3:
        # High engagement
        message = (
            f"{greeting}, it's Versiful! We noticed you've been asking questions but haven't registered yet.\\n\\n"
            "Create a free account at https://versiful.io to:\\n"
            "• Get personalized biblical guidance\\n"
            "• Choose your preferred Bible version\\n\\n"
            "What's on your heart today?"
        )
    elif engagement_level == 2:
        # Medium engagement
        message = (
            f"{greeting}, it's Versiful! It's been a while since we last connected. "
            "We're here to provide biblical guidance anytime you need it.\\n\\n"
            "Register at https://versiful.io for free to get personalized responses.\\n\\n"
            "What can we help you with today?"
        )
    else:
        # Low engagement
        message = (
            f"{greeting}! It's Versiful. It's been a while since we last connected. "
            "We're here to provide biblical guidance whenever you need it.\\n\\n"
            "Create a free account at https://versiful.io to:\\n"
            "• Personalized biblical guidance\\n"
            "• Your preferred Bible version\\n\\n"
            "Reply anytime with questions!"
        )

    return message


def main():
    # Query for registered non-subscribers
    response = users_table.scan(
        FilterExpression=Attr('isRegistered').eq(True) &
                         Attr('isSubscribed').eq(False) &
                         (Attr('skipMarketing').not_exists() | Attr('skipMarketing').eq(False))
    )

    users = response['Items']

    # Sort by createdAt to identify recent signups
    users.sort(key=lambda u: u.get('createdAt', ''), reverse=True)

    print("# Registered Non-Subscriber Outreach Plan\\n")
    print(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"**Total users:** {len(users)}\\n")
    print("---\\n")

    high_priority = []
    medium_priority = []
    low_priority = []

    for i, user in enumerate(users, 1):
        user_id = user.get('userId')
        email = user.get('email', 'N/A')
        phone = user.get('phoneNumber', '')
        first_name = user.get('firstName', '')
        last_name = user.get('lastName', '')
        created_at = user.get('createdAt', 'N/A')

        # Get message history
        messages = get_user_message_history(user_id, phone)
        user_messages = [m for m in messages if m.get('role') == 'user']

        engagement_level = len(user_messages)

        # Calculate days since creation
        days_since_created = calculate_days_ago(created_at) if created_at != 'N/A' else -1

        # Skip same-day signups
        if days_since_created == 0:
            continue

        # Calculate days since last message
        days_since_last = -1
        if user_messages:
            last_timestamp = user_messages[-1].get('timestamp', '')
            days_since_last = calculate_days_ago(last_timestamp)

        print(f"## {i}. {first_name} {last_name}".strip())
        print(f"- **Email:** {email}")
        if phone:
            print(f"- **Phone:** {phone}")
        print(f"- **User ID:** {user_id}")
        print(f"- **Created:** {created_at} ({days_since_created} days ago)")
        print(f"- **User messages sent:** {engagement_level}")

        if user_messages:
            print(f"- **Total messages in thread:** {len(messages)}")
            print(f"- **Days since last message:** {days_since_last}")

            print("\\n**Recent questions:**")
            for msg in user_messages[:3]:
                content = msg.get('content', '')
                if len(content) > 100:
                    content = content[:100] + "..."
                print(f"- \\"{content}\\"")

        print("\\n### Proposed Message")
        message = generate_message(first_name, engagement_level)
        print(f"```\\n{message}\\n```")

        # Categorize by engagement
        user_data = {
            'name': f"{first_name} {last_name}".strip() or email,
            'phone': phone,
            'engagement': engagement_level
        }

        if engagement_level >= 3:
            high_priority.append(user_data)
        elif engagement_level == 2:
            medium_priority.append(user_data)
        else:
            low_priority.append(user_data)

        print("\\n---\\n")

    # Summary
    print("\\n## Summary")
    print(f"- Total registered non-subscribers: {len(users)}")
    print(f"- High priority (3+ messages): {len(high_priority)}")
    print(f"- Medium priority (2 messages): {len(medium_priority)}")
    print(f"- Low priority (0-1 messages): {len(low_priority)}")

    if high_priority:
        print("\\n### High Priority Users")
        for u in high_priority:
            print(f"- {u['name']} ({u['phone'] or 'no phone'}): {u['engagement']} messages")

    if medium_priority:
        print("\\n### Medium Priority Users")
        for u in medium_priority:
            print(f"- {u['name']} ({u['phone'] or 'no phone'}): {u['engagement']} messages")

    if low_priority:
        print("\\n### Low Priority Users")
        for u in low_priority:
            print(f"- {u['name']} ({u['phone'] or 'no phone'}): {u['engagement']} messages")


if __name__ == "__main__":
    main()
