---
name: outreach-campaign
description: Create and execute SMS outreach campaigns for Versiful users. Use when user wants to send messages to registered non-subscribers or unregistered texters.
---

# Outreach Campaign

Comprehensive SMS outreach campaign management for Versiful. Analyzes user segments, generates personalized messages based on engagement history, creates review CSVs, and executes campaigns with proper DynamoDB logging.

## Capabilities

- Analyze registered users who haven't subscribed
- Identify unregistered users who have texted but never created accounts
- Generate personalized messages based on engagement levels and message history
- Create CSV files for campaign review
- Execute SMS campaigns via Twilio with proper logging to chat-messages table
- Follow Versiful messaging best practices (identify as "it's Versiful!", acknowledge time gaps, etc.)

## Workflow

### Phase 1: Campaign Planning
1. Identify target user segment:
   - Registered non-subscribers: Query prod-versiful-users where isRegistered=true and isSubscribed=false
   - Unregistered texters: Query prod-versiful-sms-usage and cross-reference with users table
2. Analyze message history from prod-versiful-chat-messages table
3. Calculate engagement metrics (message count, days since last contact, question patterns)
4. Exclude users with skipMarketing=true or identified as spam/test accounts

### Phase 2: Message Generation
1. Craft personalized messages based on engagement level:
   - **High engagement (3+ messages)**: Emphasize they've been asking questions, offer to save history
   - **Medium engagement (2 messages)**: Acknowledge past interaction, offer personalized guidance
   - **Low engagement (1 message)**: Light touch, offer benefits of registration
2. Apply messaging best practices:
   - Always identify as "it's Versiful!"
   - For returning users: "It's been a while since we last connected"
   - Never say "Thanks for reaching out" for old contacts
   - De-emphasize "saved conversation history" feature
   - Include registration link: https://versiful.io
   - Use first name if available
3. Generate markdown analysis document with:
   - User details and message history
   - Days since last contact
   - Proposed message for each user
   - Summary statistics by engagement level

### Phase 3: CSV Creation
1. Create CSV with columns: phone_number, first_name, engagement_level, message
2. Present to user for review
3. Allow user to exclude specific numbers or modify messages

### Phase 4: Campaign Execution
1. Set SECRET_ARN environment variable if not already set
2. Send SMS messages via Twilio using send_sms() function
3. For each message sent:
   - Look up userId by phone number
   - Log to prod-versiful-chat-messages table with:
     - threadId: phone_number
     - role: "assistant"
     - channel: "sms"
     - timestamp: current UTC time
     - messageId: new UUID
     - content: message text
     - userId: linked if found
4. Rate limit: 1 second between messages
5. Report success/failure statistics

## Resources

### Scripts
- `scripts/analyze_registered_users.py`: Analyzes registered non-subscribers and generates outreach plan
- `scripts/analyze_unregistered_texters.py`: Analyzes unregistered SMS users and generates outreach plan
- `scripts/send_campaign.py`: Executes SMS campaign from CSV with proper logging
- `scripts/generate_csv.py`: Converts analysis output to CSV format for review

### References
- `references/messaging-guidelines.md`: Best practices for Versiful outreach messages
- `references/dynamodb-schema.md`: Schema for chat-messages and users tables
- `references/example-campaigns.md`: Examples of previous successful campaigns

## DynamoDB Tables

### prod-versiful-users
- Primary key: userId
- Attributes: phoneNumber, email, firstName, lastName, isRegistered, isSubscribed, skipMarketing

### prod-versiful-sms-usage
- Tracks SMS usage by phone number
- Used to find unregistered texters

### prod-versiful-chat-messages
- Primary key: threadId (partition), timestamp (sort)
- For SMS: threadId = phone_number
- Attributes: messageId, role, content, channel, userId, phoneNumber

## Examples

### Example: Registered Non-Subscribers Campaign
User says: "Create an outreach campaign for registered users who haven't subscribed"

Actions:
1. Query DynamoDB for users with isRegistered=true, isSubscribed=false
2. Exclude users with skipMarketing=true
3. Analyze message history for each user
4. Generate personalized messages based on engagement
5. Create `user_outreach_plan.md` with analysis
6. Create `outreach_messages.csv` for review
7. Wait for user approval
8. Execute campaign with `send_campaign.py`

### Example: Unregistered Texters Campaign
User says: "Message people who texted but never registered"

Actions:
1. Scan prod-versiful-sms-usage table
2. Cross-reference with users table to find non-registered numbers
3. Query chat-messages for message history
4. Calculate days since last contact
5. Generate messages acknowledging time gap
6. Exclude spam/test numbers identified by user
7. Create `unregistered_texters_outreach.csv`
8. Execute after approval

## Message Templates

### High Engagement (3+ messages)
```
Hi [Name]! It's Versiful. We noticed you've been asking questions but haven't registered yet.

Create a free account at https://versiful.io to:
• Get personalized biblical guidance
• Choose your preferred Bible version

What's on your heart today?
```

### Medium Engagement (2 messages)
```
Hi [Name], it's Versiful! It's been a while since we last connected. We're here to provide biblical guidance anytime you need it.

Register at https://versiful.io for free to get personalized responses.

What can we help you with today?
```

### Low Engagement (1 message)
```
Hi! It's Versiful. It's been a while since we last connected. We're here to provide biblical guidance whenever you need it.

Create a free account at https://versiful.io to:
• Personalized biblical guidance
• Your preferred Bible version

Reply anytime with questions!
```

## Safety Checks

- Always confirm before sending messages (show count and ask "yes/no")
- Never send to toll-free numbers (can cause SMS loops)
- Respect skipMarketing flags
- Rate limit to avoid carrier throttling
- Log all outbound messages for audit trail
- Link messages to userId when possible for proper threading

## Environment Requirements

- AWS credentials configured
- SECRET_ARN environment variable set for Twilio access
- DynamoDB access to prod tables
- Python packages: boto3, twilio (via sms_notifications module)
