# Example Outreach Campaigns

This document contains examples of successful outreach campaigns run for Versiful.

## Campaign 1: Registered Non-Subscribers (March 2026)

**Date:** March 2026
**Target Segment:** Users who registered but never subscribed
**Total Recipients:** 12
**Send Success Rate:** 100% (12/12)

### Segmentation Criteria
- `isRegistered = true`
- `isSubscribed = false`
- `skipMarketing != true` or does not exist
- Exclude users who registered same day (too soon)
- Exclude users with explicit skipMarketing flag (5 users)

### Message Strategy
Messages were personalized based on engagement level:

#### High Priority (3+ messages sent to Versiful)
**Count:** 3 users
**Approach:** Acknowledge their engagement, emphasize personalization

**Example:**
```
Hi Madison, it's Versiful! It's been a while since we last connected. We noticed you've been asking questions but haven't registered yet.

Create a free account at https://versiful.io to:
• Get personalized biblical guidance
• Choose your preferred Bible version

What's on your heart today?
```

#### Medium Priority (2 messages)
**Count:** 6 users
**Approach:** Light reminder of service, simple value prop

**Example:**
```
Hi Greg, it's Versiful! It's been a while since we last connected. We're here to provide biblical guidance anytime you need it.

Register at https://versiful.io for free to get personalized responses.

What can we help you with today?
```

#### Low Priority (1 message)
**Count:** 3 users
**Approach:** Very light touch, open invitation

**Example:**
```
Hi! It's Versiful. It's been a while since we last connected. We're here to provide biblical guidance whenever you need it.

Create a free account at https://versiful.io to:
• Personalized biblical guidance
• Your preferred Bible version

Reply anytime with questions!
```

### Results
- Messages sent: 12/12 (100%)
- All messages logged to DynamoDB successfully
- Reply rate: (tracking in progress)
- Registration rate: (tracking in progress)

### Key Learnings
1. **Always identify as "it's Versiful!"** - Users don't have our number saved
2. **Personalize with first name when available** - Higher engagement expected
3. **Remove "saved conversation history"** - Not a compelling benefit for most users
4. **Keep messages concise** - Under 320 characters when possible

---

## Campaign 2: Unregistered Texters (March 2026)

**Date:** March 2026
**Target Segment:** Users who texted Versiful but never registered an account
**Total Recipients:** 7
**Send Success Rate:** 100% (7/7)

### Segmentation Criteria
- Phone number exists in `prod-versiful-sms-usage`
- Phone number NOT in `prod-versiful-users` with `isRegistered = true`
- Exclude spam/test accounts (identified by message content)
- Exclude test numbers (+18173088873)
- Manual review of message history

### Message Strategy
Messages customized based on engagement level and whether name was known:

#### High Engagement (7+ total messages)
**Count:** 1 user (Zach)
**Approach:** Acknowledge they've been active, emphasize registration benefits

**Example:**
```
Hi Zach, it's Versiful! It's been a while since we last connected. We noticed you've been asking questions but haven't registered yet.

Create a free account at https://versiful.io to:
• Get personalized biblical guidance
• Choose your preferred Bible version

What's on your heart today?
```

**Context:**
- 14 total messages in thread (7 user questions)
- 28 days since last message
- User provided name in conversation

#### Medium Engagement (3+ messages, with name)
**Count:** 1 user (Greg)
**Approach:** Friendly reconnection, simple value prop

**Example:**
```
Hi Greg, it's Versiful! It's been a while since we last connected. We're here to provide biblical guidance anytime you need it.

Register at https://versiful.io for free to get personalized responses.

What can we help you with today?
```

**Context:**
- 4 total messages (2 user questions)
- 72 days since last message
- Asked about scripture for meditation

#### Medium Engagement (3+ messages, no name)
**Count:** 1 user
**Approach:** Generic greeting, emphasize availability

**Example:**
```
Hi! It's Versiful. It's been a while since we last connected. We're here to provide biblical guidance anytime you need it.

Register at https://versiful.io for free to get personalized responses.

What can we help you with today?
```

**Context:**
- 6 total messages (3 questions)
- 15 days since last message
- Substantive questions (why Jesus was killed, views on masturbation)

#### Low Engagement (1 message)
**Count:** 4 users
**Approach:** Very light touch, emphasize availability

**Example:**
```
Hi! It's Versiful. It's been a while since we last connected. We're here to provide biblical guidance whenever you need it.

Create a free account at https://versiful.io to:
• Personalized biblical guidance
• Your preferred Bible version

Reply anytime with questions!
```

**Context:**
- 2 total messages (1 user question)
- 14-75 days since last message
- Minimal engagement

### Excluded Users
- **+17147178113**: Hostile/mocking questions ("Do people pay for these weak AI responses?")
- **+14845297343**: Spam ("Buh")
- **+16824356191**: Test ("?")
- **+15735513956**: Same-day contact (0 days since last message)
- **+18173088873**: Known test number

### Results
- Messages sent: 7/7 (100%)
- All messages logged to DynamoDB successfully
- Reply rate: (tracking in progress)
- Registration rate: (tracking in progress)

### Key Learnings
1. **"It's been a while" works better than "Thanks for reaching out"** - More authentic for old contacts
2. **Manual review is essential** - Caught spam and hostile users that automation missed
3. **Exclude same-day contacts** - Let them complete their current interaction first
4. **Name extraction from messages is valuable** - Can personalize even for unregistered users

---

## Message Iteration History

### Version 1: Initial Draft
❌ Issues:
- Didn't identify sender
- Said "Thanks for reaching out" for old contacts
- Included "Saved conversation history" feature

### Version 2: Added Sender Identification
✅ Improvements:
- Added "it's Versiful!" to all messages
- Recipients know who is texting them

### Version 3: Removed Conversation History
✅ Improvements:
- Removed "Saved conversation history" bullet point
- Focused on personalization and Bible version choice

### Version 4: Fixed Time Acknowledgment
✅ Improvements:
- Changed "Thanks for reaching out" to "It's been a while since we last connected"
- More appropriate for users who texted weeks/months ago
- Final version used in campaigns

---

## Timing Analysis

### Days Since Last Message Distribution

**Campaign 1: Registered Non-Subscribers**
- 0-7 days: 1 user (excluded - too recent)
- 8-30 days: 4 users
- 31-60 days: 3 users
- 61+ days: 5 users

**Campaign 2: Unregistered Texters**
- 0-7 days: 1 user (excluded - same day)
- 8-30 days: 3 users
- 31-60 days: 1 user
- 61+ days: 3 users

### Optimal Timing Window
Based on exclusions and engagement:
- **Too soon:** 0-7 days (let current interaction complete)
- **Optimal:** 14-60 days (not too soon, not too cold)
- **Still viable:** 60-90 days (getting cold but still worthwhile)
- **Last chance:** 90+ days (very cold, low expected response)

---

## Technical Implementation

### Script Workflow
1. **analyze_registered_users.py** or **analyze_unregistered_texters.py**
   - Query DynamoDB for target segment
   - Analyze message history
   - Calculate engagement metrics
   - Generate markdown analysis document

2. **Manual CSV Creation**
   - Review analysis document
   - Create CSV with columns: phone_number, first_name, engagement_level, message
   - Exclude spam/test users
   - Adjust messages based on user feedback

3. **send_outreach_messages.py**
   - Read CSV file
   - Confirm send with user (show count)
   - For each row:
     - Send SMS via Twilio
     - Look up userId by phone number
     - Log to chat-messages table
     - Rate limit (1 second between sends)
   - Report success/failure statistics

### Environment Setup
```bash
export SECRET_ARN="arn:aws:secretsmanager:us-east-1:018908982481:secret:prod-versiful_secrets-1xcowv"
```

### CSV Format
```csv
phone_number,first_name,engagement_level,message
+18005551234,John,2,"Hi John, it's Versiful! It's been a while..."
+18005555678,,1,"Hi! It's Versiful. It's been a while..."
```

### DynamoDB Logging
```python
message_item = {
    'threadId': phone_number,          # E.164 phone number
    'timestamp': timestamp,            # ISO 8601
    'messageId': str(uuid4()),        # Unique ID
    'role': 'assistant',              # Outbound message
    'content': message,               # Message text
    'channel': 'sms',                # Channel identifier
    'createdAt': timestamp,
    'updatedAt': timestamp,
    'phoneNumber': phone_number,
    'userId': user_id                # If found
}
```

---

## Future Enhancements

### Potential Improvements
1. **Automated CSV generation** - Skip manual step
2. **A/B testing framework** - Test message variations systematically
3. **Reply tracking** - Measure campaign effectiveness
4. **Conversion tracking** - Track registrations post-outreach
5. **Automated exclusions** - Flag spam/test users automatically
6. **Timing optimization** - Send at optimal times for user timezone
7. **Follow-up sequences** - Second touch for non-responders after 14 days

### Metrics to Track
- Reply rate by segment
- Registration rate by segment
- Time to reply
- Sentiment of replies
- Unsubscribe/STOP rate
- Message deliverability rate

### Testing Ideas
- Different greetings ("Hi!" vs "Hi [Name]")
- Different CTAs ("What's on your heart?" vs "Reply anytime")
- Different value props (personalization vs convenience)
- Different urgency levels (none vs light)
- Emoji usage (none vs strategic)
