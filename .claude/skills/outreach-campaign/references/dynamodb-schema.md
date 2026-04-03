# DynamoDB Schema Reference for Outreach Campaigns

## prod-versiful-users

**Purpose:** Stores user account information and preferences.

### Primary Key
- **Partition Key:** `userId` (String) - Unique identifier from Cognito

### Key Attributes

| Attribute | Type | Description | Example |
|-----------|------|-------------|---------|
| userId | String | Cognito user ID | "12345678-1234-1234-1234-123456789012" |
| email | String | User email address | "user@example.com" |
| phoneNumber | String | E.164 format phone | "+18005551234" |
| firstName | String | User first name | "John" |
| lastName | String | User last name | "Doe" |
| isRegistered | Boolean | Has completed registration | true |
| isSubscribed | Boolean | Has active subscription | false |
| skipMarketing | Boolean | Opt-out of marketing messages | false |
| createdAt | String | ISO timestamp of account creation | "2026-01-15T10:30:00Z" |
| preferredBibleVersion | String | User's Bible translation choice | "ESV" |

### Query Patterns for Outreach

#### Find registered non-subscribers
```python
response = users_table.scan(
    FilterExpression='isRegistered = :reg AND isSubscribed = :sub AND attribute_not_exists(skipMarketing)',
    ExpressionAttributeValues={
        ':reg': True,
        ':sub': False
    }
)
```

#### Find registered non-subscribers (including explicit skipMarketing=false)
```python
from boto3.dynamodb.conditions import Attr

response = users_table.scan(
    FilterExpression=Attr('isRegistered').eq(True) &
                     Attr('isSubscribed').eq(False) &
                     (Attr('skipMarketing').not_exists() | Attr('skipMarketing').eq(False))
)
```

#### Look up user by phone number
```python
response = users_table.scan(
    FilterExpression='phoneNumber = :phone',
    ExpressionAttributeValues={':phone': '+18005551234'}
)
user_id = response['Items'][0]['userId'] if response['Items'] else None
```

## prod-versiful-sms-usage

**Purpose:** Tracks SMS message counts and usage by phone number.

### Primary Key
- **Partition Key:** `phoneNumber` (String) - E.164 format

### Key Attributes

| Attribute | Type | Description | Example |
|-----------|------|-------------|---------|
| phoneNumber | String | E.164 format phone | "+18005551234" |
| messagesSent | Number | Count of outbound messages | 5 |
| messagesReceived | Number | Count of inbound messages | 3 |
| lastMessageDate | String | ISO timestamp of last message | "2026-02-15T14:22:00Z" |
| totalCost | Number | Total SMS cost in USD | 0.0225 |

### Query Patterns for Outreach

#### Find all phone numbers with SMS usage
```python
response = sms_usage_table.scan()
phone_numbers = [item['phoneNumber'] for item in response['Items']]
```

#### Find unregistered texters
```python
# 1. Get all phone numbers from SMS usage
sms_response = sms_usage_table.scan()
sms_phones = {item['phoneNumber']: item.get('messagesSent', 0)
              for item in sms_response['Items']}

# 2. Get all registered phone numbers
users_response = users_table.scan(
    ProjectionExpression='phoneNumber',
    FilterExpression='attribute_exists(phoneNumber)'
)
registered_phones = {item['phoneNumber'] for item in users_response['Items']}

# 3. Find phones in SMS usage but not in users
unregistered = {phone: count for phone, count in sms_phones.items()
                if phone not in registered_phones}
```

## prod-versiful-chat-messages

**Purpose:** Stores all chat messages across channels (web, SMS).

### Primary Key
- **Partition Key:** `threadId` (String) - Conversation identifier
- **Sort Key:** `timestamp` (String) - ISO 8601 timestamp

### Key Attributes

| Attribute | Type | Description | Example |
|-----------|------|-------------|---------|
| threadId | String | For SMS: phoneNumber; For web: userId | "+18005551234" or "user-id-123" |
| timestamp | String | ISO 8601 timestamp | "2026-02-15T14:22:33.123456Z" |
| messageId | String | UUID for this message | "a1b2c3d4-e5f6-g7h8-i9j0-k1l2m3n4o5p6" |
| role | String | "user" or "assistant" | "user" |
| content | String | Message text | "What does the Bible say about forgiveness?" |
| channel | String | "sms" or "web" | "sms" |
| userId | String | Linked user ID (if known) | "12345678-1234-1234-1234-123456789012" |
| phoneNumber | String | Phone number (for SMS channel) | "+18005551234" |
| createdAt | String | ISO timestamp | "2026-02-15T14:22:33Z" |
| updatedAt | String | ISO timestamp | "2026-02-15T14:22:33Z" |

### Message Structure by Channel

#### SMS Messages (Inbound)
```python
{
    'threadId': '+18005551234',  # Phone number
    'timestamp': '2026-02-15T14:22:33.123456Z',
    'messageId': 'uuid-here',
    'role': 'user',
    'content': 'User question here',
    'channel': 'sms',
    'phoneNumber': '+18005551234',
    'userId': 'user-id-if-registered',  # Optional
    'createdAt': '2026-02-15T14:22:33Z',
    'updatedAt': '2026-02-15T14:22:33Z'
}
```

#### SMS Messages (Outbound - from outreach)
```python
{
    'threadId': '+18005551234',  # Phone number
    'timestamp': '2026-03-01T10:00:00.000000Z',
    'messageId': str(uuid4()),
    'role': 'assistant',
    'content': 'Hi Greg, it\'s Versiful! It\'s been a while...',
    'channel': 'sms',
    'phoneNumber': '+18005551234',
    'userId': 'user-id-if-found',  # Optional
    'createdAt': '2026-03-01T10:00:00Z',
    'updatedAt': '2026-03-01T10:00:00Z'
}
```

### Query Patterns for Outreach

#### Get message history for a phone number
```python
response = messages_table.query(
    KeyConditionExpression='threadId = :tid',
    ExpressionAttributeValues={':tid': '+18005551234'},
    ScanIndexForward=True  # Oldest first
)
messages = response['Items']
```

#### Get only user messages (not assistant responses)
```python
response = messages_table.query(
    KeyConditionExpression='threadId = :tid',
    FilterExpression='#role = :user_role',
    ExpressionAttributeNames={'#role': 'role'},
    ExpressionAttributeValues={
        ':tid': '+18005551234',
        ':user_role': 'user'
    },
    ScanIndexForward=True
)
user_messages = response['Items']
```

#### Calculate engagement metrics
```python
response = messages_table.query(
    KeyConditionExpression='threadId = :tid',
    ExpressionAttributeValues={':tid': '+18005551234'},
    ScanIndexForward=True
)

messages = response['Items']
user_messages = [m for m in messages if m.get('role') == 'user']
total_messages = len(messages)
user_question_count = len(user_messages)

if user_messages:
    first_timestamp = user_messages[0]['timestamp']
    last_timestamp = user_messages[-1]['timestamp']

    # Calculate days since last message
    from datetime import datetime
    last_date = datetime.fromisoformat(last_timestamp.replace('Z', '+00:00'))
    days_ago = (datetime.now(last_date.tzinfo) - last_date).days
```

#### Log outbound outreach message
```python
from uuid import uuid4
from datetime import datetime, timezone

def log_outbound_message(phone_number: str, message: str, user_id: str = None):
    timestamp = datetime.now(timezone.utc).isoformat()

    message_item = {
        'threadId': phone_number,
        'timestamp': timestamp,
        'messageId': str(uuid4()),
        'role': 'assistant',
        'content': message,
        'channel': 'sms',
        'createdAt': timestamp,
        'updatedAt': timestamp,
        'phoneNumber': phone_number
    }

    if user_id:
        message_item['userId'] = user_id

    messages_table.put_item(Item=message_item)
```

## Important Notes

### Phone Number Format
- Always use E.164 format: `+[country code][number]`
- Example: `+18005551234` (US number)
- Never use: `(800) 555-1234`, `800-555-1234`, or `8005551234`

### Threading for SMS
- For SMS, `threadId` is ALWAYS the phone number in E.164 format
- This allows all messages (user and assistant) to be in the same thread
- When logging outbound outreach, use phone number as threadId

### User ID Linking
- For unregistered users, `userId` may not exist
- Always look up userId by phone number before logging outbound messages
- This allows proper linking if user registers later

### Timestamp Format
- Use ISO 8601 format with timezone: `2026-02-15T14:22:33.123456Z`
- Python: `datetime.now(timezone.utc).isoformat()`
- Include microseconds for sort key uniqueness

### Boolean Attributes
- DynamoDB doesn't have NULL booleans
- Check for attribute existence: `attribute_not_exists(skipMarketing)`
- Or explicit false: `skipMarketing = :false`

### Scan vs Query
- **Query**: Use when you have the partition key (threadId for messages)
- **Scan**: Use for users table when searching by phoneNumber or isRegistered
- Scans are expensive - use sparingly and filter in application when possible
