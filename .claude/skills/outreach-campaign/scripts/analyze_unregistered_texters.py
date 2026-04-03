#!/usr/bin/env python3
"""
Analyze unregistered texters and their message history.

Usage:
    python .claude/skills/outreach-campaign/scripts/analyze_unregistered_texters.py

Output:
    - Prints markdown analysis to stdout
    - Use > to redirect to file: python script.py > unregistered_texters_plan.md
"""

import boto3
from datetime import datetime

dynamodb = boto3.resource('dynamodb')
messages_table = dynamodb.Table('prod-versiful-chat-messages')
sms_usage_table = dynamodb.Table('prod-versiful-sms-usage')
users_table = dynamodb.Table('prod-versiful-users')


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


def get_name_from_messages(phone_number: str, messages: list) -> str:
    """Try to extract name from message history."""
    for msg in messages:
        if msg.get('role') == 'user':
            content = msg.get('content', '').lower()
            # Look for "I'm [Name]" or "My name is [Name]"
            if "i'm " in content or "my name is " in content:
                # Simple extraction - could be improved
                parts = content.replace("i'm", "my name is").split("my name is")
                if len(parts) > 1:
                    name_part = parts[1].strip().split()[0]
                    return name_part.capitalize()
    return ""


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

    if engagement_level >= 7:
        # Very high engagement
        message = (
            f"{greeting}, it's Versiful! It's been a while since we last connected. "
            "We noticed you've been asking questions but haven't registered yet.\\n\\n"
            "Create a free account at https://versiful.io to:\\n"
            "• Get personalized biblical guidance\\n"
            "• Choose your preferred Bible version\\n\\n"
            "What's on your heart today?"
        )
    elif engagement_level >= 3:
        # Medium-high engagement
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
    # Get all SMS usage
    sms_response = sms_usage_table.scan()
    sms_usage = sms_response.get('Items', [])

    # Filter to unregistered
    unregistered = []
    for item in sms_usage:
        phone = item.get('phoneNumber')
        if phone and not is_registered(phone):
            unregistered.append({
                'phone': phone,
                'messagesSent': item.get('messagesSent', 0)
            })

    # Sort by message count descending
    unregistered.sort(key=lambda x: x['messagesSent'], reverse=True)

    print("# Unregistered Texter Outreach Plan\\n")
    print(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"**Total users:** {len(unregistered)}\\n")
    print("---\\n")

    for i, item in enumerate(unregistered, 1):
        phone = item['phone']
        msg_count = item['messagesSent']

        print(f"## {i}. {phone}")
        print(f"- **Messages sent:** {msg_count}")

        # Get message history
        try:
            response = messages_table.query(
                KeyConditionExpression='threadId = :tid',
                ExpressionAttributeValues={':tid': phone},
                ScanIndexForward=True  # Oldest first
            )

            messages = response['Items']

            if messages:
                user_messages = [m for m in messages if m.get('role') == 'user']

                # Try to extract name
                first_name = get_name_from_messages(phone, messages)

                print(f"- **Total messages in thread:** {len(messages)}")
                print(f"- **User questions:** {len(user_messages)}")

                if user_messages:
                    print(f"- **First message:** {user_messages[0].get('timestamp', 'N/A')}")
                    print(f"- **Last message:** {user_messages[-1].get('timestamp', 'N/A')}")

                    print("\\n**Questions asked:**")
                    for msg in user_messages[:3]:  # Show first 3
                        content = msg.get('content', '')
                        if len(content) > 100:
                            content = content[:100] + "..."
                        print(f"- \\"{content}\\"")

                    # Calculate days since last message
                    last_timestamp = user_messages[-1].get('timestamp', '')
                    if last_timestamp:
                        days_ago = calculate_days_ago(last_timestamp)
                        print(f"\\n**Days since last message:** {days_ago}")

                        # Skip same-day contacts
                        if days_ago == 0:
                            print("\\n*Note: Same-day contact - skip for now*")
                            print("\\n---\\n")
                            continue

                # Generate message
                print("\\n### Proposed Message")
                engagement_level = len(user_messages) if messages else msg_count
                message = generate_message(first_name, engagement_level)
                print(f"```\\n{message}\\n```")

            else:
                print(f"- **No message history found**")

        except Exception as e:
            print(f"- **Error fetching messages:** {str(e)}")

        print("\\n---\\n")

    print("\\n## Summary")
    print(f"- Total unregistered texters: {len(unregistered)}")
    high_engagement = sum(1 for x in unregistered if x['messagesSent'] >= 3)
    medium_engagement = sum(1 for x in unregistered if x['messagesSent'] == 2)
    low_engagement = sum(1 for x in unregistered if x['messagesSent'] == 1)
    print(f"- High engagement (3+ messages): {high_engagement}")
    print(f"- Medium engagement (2 messages): {medium_engagement}")
    print(f"- Low engagement (1 message): {low_engagement}")


if __name__ == "__main__":
    main()
