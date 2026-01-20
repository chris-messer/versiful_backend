# Message Cost Tracking Implementation Summary

## Overview
This document summarizes all changes made to implement comprehensive message cost tracking for both GPT (OpenAI) and Twilio SMS costs.

## Changes Made

### 1. DynamoDB Schema Updates

#### `chat-messages` Table
Added new attributes and indexes:
- **`messageId`** (String): UUID for every message (user and assistant)
- **`twilioSid`** (String): Twilio Message SID (top-level column for SMS messages)
- **`costs`** (Map): Nested structure storing cost data
  - `costs.gpt`: OpenAI GPT costs (model, tokens, USD)
  - `costs.twilio`: Twilio SMS costs (price, priceUnit, status, numSegments)

**New Global Secondary Indexes:**
1. **`MessageUuidIndex`**: Query by `messageId` (hash) + `timestamp` (range)
   - Used for: Looking up messages by UUID for cost updates, correlation
2. **`TwilioSidIndex`**: Query by `twilioSid` (hash)
   - Used for: Looking up messages by Twilio SID from callbacks

**File:** `terraform/modules/lambdas/_chat_tables.tf`

---

### 2. New Modules Created

#### `lambdas/shared/cost_calculator.py`
Calculates OpenAI GPT costs based on token usage.

**Features:**
- Pricing lookup for GPT-4o, GPT-4o-mini, and other models
- Calculates cost from input/output tokens
- Returns costs as `Decimal` for DynamoDB compatibility

**Usage:**
```python
from lambdas.shared.cost_calculator import calculate_gpt_cost

cost = calculate_gpt_cost('gpt-4o', input_tokens=1500, output_tokens=500)
# Returns: Decimal('0.008750')  # $0.00875 USD
```

---

#### `lambdas/shared/sms_operations.py`
**Unified SMS operations module** - THE ONLY place where SMS messages are sent and received.

**Key Functions:**
1. **`receive_sms()`**: Logs all inbound SMS
   - Stores to DynamoDB with `messageId` (UUID) and `twilioSid` (top-level)
   - Sends PostHog `sms_inbound` event

2. **`send_sms()`**: Sends all outbound SMS via Twilio
   - Creates/updates DynamoDB record with `messageId` and `twilioSid`
   - Configures Twilio StatusCallback URL with `message_uuid` query parameter
   - Sends PostHog `sms_outbound` event
   - Supports MMS (media_url for vCards, images)

3. **`update_sms_cost()`**: Updates message with Twilio cost data
   - Looks up message by `messageId` using `MessageUuidIndex`
   - Stores cost in `costs.twilio` 
   - Sends PostHog `sms_cost_update` event

**StatusCallback URL Format:**
```
https://api.{env}.versiful.io/sms/callback?message_uuid={message_uuid}
```

**Important:** Twilio price data takes **20-30 minutes** to populate. Callbacks receive the message status (sent/delivered) but NOT the price initially.

---

#### `lambdas/sms/twilio_callback_handler.py`
Lambda function that receives Twilio status callbacks.

**Flow:**
1. Twilio sends POST to `/sms/callback?message_uuid={uuid}`
2. Lambda extracts `message_uuid` from query string
3. Parses callback body for `MessageSid`, `MessageStatus`, `Price`, etc.
4. If price available, calls `update_sms_cost()`
5. Returns 200 OK to Twilio

**Note:** Price is often NOT included in callbacks. A polling mechanism is needed to back-fill costs.

---

### 3. Modified Modules

#### `lambdas/chat/agent_service.py`
**Changes:**
- Added `message_uuid` parameter to `process_message()`, `_generate_llm_response()`, and `_create_posthog_callback()`
- Modified PostHog callback handler to include `message_uuid` property
- Extracts `usage_metadata` from LLM responses
- Calculates GPT cost using `cost_calculator.calculate_gpt_cost()`
- Returns cost data in response: `usage: {model, inputTokens, outputTokens, totalTokens, costUsd}`

**PostHog $ai_generation Event Properties:**
```python
{
  "conversation_id": session_id,
  "$ai_session_id": session_id,
  "channel": "sms" | "web",
  "message_uuid": "uuid-here"  # NEW - for correlation
}
```

---

#### `lambdas/chat/chat_handler.py`
**Changes:**
- Generates `user_message_id` (UUID) for every user message
- Passes `user_message_id` to agent for PostHog correlation
- Skips saving user message if channel is 'sms' (already logged by `sms_operations.receive_sms()`)
- Stores GPT cost data in assistant message:
  ```python
  costs = {
    'gpt': {
      'model': 'gpt-4o',
      'inputTokens': 1500,
      'outputTokens': 500,
      'totalTokens': 2000,
      'costUsd': Decimal('0.008750')
    }
  }
  ```
- Returns `assistant_message_id` for SMS tracking

---

#### `lambdas/sms/sms_handler.py`
**Changes:**
- Imports `receive_sms()` and `send_sms()` from `sms_operations`
- Uses `receive_sms()` to log all inbound SMS with `message_uuid` and `twilio_sid`
- Uses `send_sms()` for responses, passing `assistant_message_id` to update existing message with Twilio SID
- All SMS logging now happens ONLY in `sms_operations.py` (DRY principle)

---

#### `lambdas/shared/sms_notifications.py`
**Changes:**
- Removed direct Twilio client usage
- Now uses `sms_operations.send_sms()` for ALL notifications:
  - Welcome messages (with vCard MMS)
  - Subscription confirmations
  - Cancellation messages
  - First-time texter welcomes
- All messages automatically get `message_uuid`, Twilio SID tracking, and PostHog events

---

### 4. Terraform Infrastructure

#### `terraform/modules/lambdas/main.tf`
**Changes:**
- Updated `null_resource.package_layer` triggers to watch for changes in:
  - `cost_calculator.py`
  - `sms_operations.py`
- Ensures Lambda layer rebuilds when shared modules change

#### `terraform/modules/lambdas/_sms.tf`
**Changes:**
- Added `twilio_callback_function` Lambda
- Added Lambda permissions for API Gateway invocation
- Added API Gateway route: `POST /sms/callback`
- Added environment variables for callback handler (CHAT_MESSAGES_TABLE, POSTHOG_API_KEY)

---

## Data Flow

### SMS Message Flow (Outbound)
```
1. User sends SMS to Versiful
2. sms_handler receives from Twilio webhook
3. sms_operations.receive_sms() logs to DynamoDB:
   - messageId: uuid (NEW)
   - twilioSid: "SM..." (NEW - top level)
   - content, timestamp, etc.
   - Sends PostHog sms_inbound event
4. chat_handler.process_chat_message() generates response
5. agent_service extracts GPT costs, sends to PostHog $ai_generation event
6. chat_handler saves assistant message with costs.gpt
7. sms_operations.send_sms() updates message with Twilio SID:
   - Calls Twilio API with StatusCallback URL
   - Updates DynamoDB with twilioSid
   - Sends PostHog sms_outbound event
8. [20-30 mins later] Twilio sends status callback
9. twilio_callback_handler receives callback
10. sms_operations.update_sms_cost() stores costs.twilio in DynamoDB
11. Sends PostHog sms_cost_update event
```

### PostHog Events for Reporting

#### Event 1: `$ai_generation` (LangChain auto-generated)
```json
{
  "event": "$ai_generation",
  "distinct_id": "user_id" | "phone_digits",
  "properties": {
    "conversation_id": "thread_id",
    "channel": "sms" | "web",
    "message_uuid": "uuid",  // Correlation key
    "$ai_session_id": "session_id",
    "$ai_input": "...",
    "$ai_output": "...",
    "$ai_input_tokens": 1500,
    "$ai_output_tokens": 500,
    "$ai_model": "gpt-4o"
    // Note: Cost calculated separately, not in event
  }
}
```

#### Event 2: `sms_inbound`
```json
{
  "event": "sms_inbound",
  "distinct_id": "user_id" | "phone_digits",
  "properties": {
    "message_uuid": "uuid",  // Correlation key
    "twilio_sid": "SM...",   // NEW
    "thread_id": "phone",
    "from": "+1234567890",
    "to": "+18336811158",
    "direction": "inbound",
    "segments": 1,
    "channel": "sms",
    "user_id": "user_id",    // NEW - for joining
    "timestamp": "ISO8601"
  }
}
```

#### Event 3: `sms_outbound`
```json
{
  "event": "sms_outbound",
  "distinct_id": "user_id" | "phone_digits",
  "properties": {
    "message_uuid": "uuid",  // Correlation key
    "twilio_sid": "SM...",   // NEW
    "thread_id": "phone",
    "from": "+18336811158",
    "to": "+1234567890",
    "direction": "outbound",
    "message_type": "chat" | "welcome" | "notification",
    "segments": 1,
    "channel": "sms",
    "user_id": "user_id",    // NEW - for joining
    "timestamp": "ISO8601"
  }
}
```

#### Event 4: `sms_cost_update`
```json
{
  "event": "sms_cost_update",
  "distinct_id": "user_id" | "phone_digits",
  "properties": {
    "message_uuid": "uuid",  // Correlation key
    "twilio_sid": "SM...",   // NEW
    "price": 0.00830,        // USD
    "price_unit": "USD",
    "status": "delivered",
    "segments": 1,
    "direction": "inbound" | "outbound",
    "user_id": "user_id",    // NEW - for joining
    "timestamp": "ISO8601"
  }
}
```

---

## PostHog Reporting

### Cost Report Query Strategy

To build a comprehensive cost report in PostHog:

1. **GPT Costs per User:**
   - Query: `$ai_generation` events
   - Group by: `distinct_id` (user_id)
   - Calculate: Token usage × model rates (use `cost_calculator` pricing)
   - Filter by: `channel` (to separate web vs SMS)

2. **Twilio Costs per User:**
   - Query: `sms_cost_update` events
   - Group by: `user_id` property
   - Sum: `price` field
   - Note: Includes both inbound and outbound (check `direction`)

3. **Message Volume per User:**
   - Inbound: Count `sms_inbound` events, group by `user_id`
   - Outbound: Count `sms_outbound` events, group by `user_id`

4. **Correlation (Message-level costs):**
   - Join `$ai_generation` and `sms_cost_update` on `message_uuid`
   - Provides: GPT cost + Twilio cost per message

---

## DynamoDB Queries

### Get Message by UUID
```python
response = messages_table.query(
    IndexName='MessageUuidIndex',
    KeyConditionExpression='messageId = :mid',
    ExpressionAttributeValues={':mid': message_uuid}
)
```

### Get Message by Twilio SID
```python
response = messages_table.query(
    IndexName='TwilioSidIndex',
    KeyConditionExpression='twilioSid = :sid',
    ExpressionAttributeValues={':sid': 'SM...'}
)
```

### Get Messages with Costs
```python
response = messages_table.query(
    KeyConditionExpression='threadId = :tid',
    ExpressionAttributeValues={':tid': thread_id},
    FilterExpression='attribute_exists(costs)'
)
```

---

## Known Limitations & Future Work

### 1. Twilio Cost Data Delay ⚠️
**Issue:** Twilio price data takes 20-30+ minutes to populate.
- Callbacks receive status but NOT price initially
- Price field is `null` in Twilio API for ~25 minutes after delivery

**Current State:** 
- ✅ StatusCallback infrastructure is working
- ✅ Callbacks are received with `message_uuid`
- ❌ Price data is not available immediately

**Solution Needed:**
Implement a scheduled Lambda (EventBridge trigger) that:
- Runs every 30-60 minutes
- Queries DynamoDB for messages without `costs.twilio` older than 30 minutes
- Polls Twilio API for each message by SID
- Updates DynamoDB with cost data
- Sends PostHog `sms_cost_update` events

**Recommended Schedule:** Every 1 hour, check messages from 30-90 minutes ago

---

### 2. Web Messages Don't Have Twilio SID
Web chat messages won't have `twilioSid` since they're not SMS. This is expected and correct.

**Filter in reports:** Use `channel = 'sms'` to get only SMS messages with Twilio costs.

---

### 3. Historical Messages Missing Data
Messages sent before this implementation won't have:
- `messageId` (UUID)
- `twilioSid` (top-level)
- `costs` structure

**Recommendation:** Accept this and only track costs going forward. Attempting to backfill would be complex and error-prone.

---

## Testing

### Dev Environment
All changes have been deployed to `dev` environment. Test with:

```bash
# Send test SMS to dev number
# Check logs:
aws logs tail /aws/lambda/dev-sms_function --since 5m --region us-east-1
aws logs tail /aws/lambda/dev-twilio_callback_function --since 5m --region us-east-1

# Check DynamoDB
aws dynamodb query --table-name dev-versiful-chat-messages \
  --index-name MessageUuidIndex \
  --key-condition-expression "messageId = :mid" \
  --expression-attribute-values '{":mid":{"S":"your-uuid-here"}}'
```

### Verified Working ✅
1. StatusCallback URLs are configured on all outbound SMS
2. Callbacks are received by Lambda with correct `message_uuid`
3. Messages are stored in DynamoDB with `messageId` and `twilioSid`
4. GPT costs are calculated and stored immediately
5. PostHog events are sent correctly

### Pending ⏳
- Twilio cost polling implementation
- Prod deployment (after dev testing confirmed)

---

## Deployment

### Apply to Dev Only (Current State)
```bash
cd terraform
../scripts/tf-env.sh dev apply -auto-approve
```

### To Deploy to Prod (After Approval)
```bash
cd terraform
../scripts/tf-env.sh prod apply
# Review plan carefully, then approve
```

---

## Summary

**What's Working:**
✅ Message UUIDs on all messages
✅ Twilio SID stored at top level in DynamoDB
✅ GPT costs calculated and stored immediately
✅ StatusCallback infrastructure fully functional
✅ PostHog events with all correlation keys
✅ DRY architecture - single source of truth for SMS operations

**What Needs Work:**
⏳ Twilio cost polling (price data delayed 20-30 min)
⏳ Prod deployment (awaiting approval)

**Architecture Wins:**
🎯 Single `sms_operations.py` module for all SMS
🎯 Correlation via `message_uuid` across all systems
🎯 Comprehensive PostHog tracking for cost reporting
🎯 Clean separation of concerns

