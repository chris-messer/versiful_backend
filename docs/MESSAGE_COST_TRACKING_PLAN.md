# Message Cost Tracking Implementation Plan

## Overview
This document outlines the implementation plan for comprehensive message cost tracking in Versiful, covering both GPT costs and Twilio SMS costs, with logging to DynamoDB and PostHog.

## Answers to Your Questions

### A. SMS Logging Module Location
**Solution**: Create a shared `message_logger.py` module in `lambdas/shared/` that centralizes all message logging for:
- SMS inbound/outbound
- GPT generations
- Welcome messages
- System notifications

This module will handle:
- UUID generation
- DynamoDB writes to chat-messages
- PostHog event tracking
- Cost tracking (when available)

### B. Twilio Cost Data Source
**Solution**: Use Twilio's Message resource `price` field, which becomes available after message processing:
- **Method 1 (Recommended)**: Status Callback webhooks - Twilio sends status updates with price information
- **Method 2 (Fallback)**: Poll/fetch the Message resource after delivery to get the `price` field
- The price field includes `price` (amount) and `price_unit` (e.g., "USD")

**Implementation**: 
1. Add status callback URL to all Twilio message sends
2. Create a new Lambda to handle Twilio status callbacks
3. Update DynamoDB chat-messages records with cost when callback is received

### C. DynamoDB Partition Key Pattern
**Current Pattern**: `threadId` (PK) + `timestamp` (SK)

**Solution**: Keep current pattern but add a **Global Secondary Index (GSI)** for UUID lookups:
- **GSI Name**: `MessageUuidIndex`
- **GSI PK**: `messageId` (the UUID)
- **GSI SK**: `timestamp`
- **Projection**: ALL

This allows:
- Efficient queries by threadId (existing pattern)
- Efficient lookups by UUID when matching with Twilio costs
- No disruption to existing queries

### D. OpenAI Cost Data Source
**How PostHog Gets Costs**: PostHog's LangChain integration automatically captures token usage from the LLM response's `usage` field.

**Where to Get Costs**: 
- OpenAI API responses include a `usage` object with:
  - `prompt_tokens` (input tokens)
  - `completion_tokens` (output tokens)
  - `total_tokens`
- Calculate cost using model pricing:
  - GPT-4o: $2.50 per 1M input tokens, $10.00 per 1M output tokens
  - GPT-4o-mini: $0.15 per 1M input tokens, $0.60 per 1M output tokens

**Implementation**: 
1. Capture `response.usage` from LangChain/OpenAI responses
2. Calculate cost based on model and token counts
3. Store in DynamoDB and send to PostHog

## Schema Changes

### chat-messages Table Updates

**New Attributes**:
```python
{
    # Existing fields
    'threadId': str,          # PK
    'timestamp': str,         # SK (ISO 8601)
    'messageId': str,         # UUID (already exists!)
    'role': str,              # "user" or "assistant"
    'content': str,
    'channel': str,           # "sms" or "web"
    
    # NEW: Cost tracking fields
    'costs': {
        'gpt': {
            'model': str,              # e.g., "gpt-4o"
            'inputTokens': int,        # prompt tokens
            'outputTokens': int,       # completion tokens
            'totalTokens': int,        # total tokens
            'costUsd': Decimal,        # calculated cost in USD
            'timestamp': str           # when cost was calculated
        },
        'twilio': {
            'messageSid': str,         # Twilio message SID
            'price': Decimal,          # from Twilio (can be negative for inbound)
            'priceUnit': str,          # e.g., "USD"
            'numSegments': int,        # number of SMS segments
            'status': str,             # "sent", "delivered", "failed", etc.
            'timestamp': str           # when cost was received
        }
    },
    
    # Existing optional fields
    'userId': str,
    'phoneNumber': str,
    'metadata': dict
}
```

**New GSI**:
```
Name: MessageUuidIndex
Partition Key: messageId (String)
Sort Key: timestamp (String)
Projection: ALL
```

## Implementation Steps

### 1. Update DynamoDB Schema (Terraform)
**File**: `terraform/modules/lambdas/_chat_tables.tf`

Add GSI to chat_messages table:
```hcl
global_secondary_index {
  name            = "MessageUuidIndex"
  hash_key        = "messageId"
  range_key       = "timestamp"
  projection_type = "ALL"
}
```

### 2. Create Shared Message Logger
**File**: `lambdas/shared/message_logger.py`

Functions:
- `log_message()` - Main function to log any message
- `update_message_cost()` - Update cost fields for existing message
- `log_to_posthog()` - Send events to PostHog

### 3. Update Agent Service (GPT Cost Tracking)
**File**: `lambdas/chat/agent_service.py`

Modifications:
- Capture `response.usage` from LangChain responses
- Calculate costs using model pricing
- Return usage/cost data in process_message() result
- Include in PostHog callback properties

### 4. Update Chat Handler
**File**: `lambdas/chat/chat_handler.py`

Modifications:
- Update `save_message()` to accept costs parameter
- Extract usage/cost from agent result
- Save costs to DynamoDB with message
- Update PostHog events with messageId

### 5. Create SMS Logger Module
**File**: `lambdas/shared/sms_logger.py`

Functions:
- `log_sms_sent()` - Log outbound SMS with messageId
- `log_sms_received()` - Log inbound SMS with messageId
- Track Twilio SID to messageId mapping for callback matching

### 6. Create Twilio Status Callback Handler
**File**: `lambdas/sms/twilio_callback_handler.py`

New Lambda to:
- Receive Twilio status callbacks
- Extract price, status, SID
- Look up messageId by Twilio SID (or by threadId + timestamp)
- Update chat-messages with Twilio cost data
- Send PostHog event with cost update

### 7. Update SMS Handler
**File**: `lambdas/sms/sms_handler.py`

Modifications:
- Use shared SMS logger for all sends
- Add status callback URL to Twilio sends
- Send PostHog events for inbound/outbound SMS

### 8. Update SMS Notifications
**File**: `lambdas/shared/sms_notifications.py`

Modifications:
- Use shared SMS logger for welcome/cancellation messages
- Track all system-initiated messages

### 9. Add Twilio Callback API Endpoint
**File**: `terraform/modules/lambdas/_sms.tf`

Add new API Gateway route and Lambda for Twilio callbacks:
- Route: `POST /sms/callback`
- Public endpoint (Twilio needs to access it)
- Lambda: twilio-callback-handler

## Model Pricing (as of 2026)

### OpenAI Pricing
```python
MODEL_PRICING = {
    'gpt-4o': {
        'input': 2.50,   # per 1M tokens
        'output': 10.00
    },
    'gpt-4o-mini': {
        'input': 0.15,
        'output': 0.60
    },
    'gpt-4-turbo': {
        'input': 10.00,
        'output': 30.00
    }
}
```

### Twilio Pricing (Approximate)
- Outbound SMS (US): ~$0.0079 per segment
- Inbound SMS (US): ~$0.0079 per segment
- Actual costs come from Twilio API (vary by carrier, country)

## PostHog Events

### New Event: `sms_inbound`
```javascript
{
  event: 'sms_inbound',
  properties: {
    message_uuid: 'uuid',
    thread_id: 'phone_number',
    from: '+1234567890',
    to: '+1987654321',
    body: 'message content',
    twilio_sid: 'SM...',
    segments: 1,
    timestamp: '2026-01-20T...',
    channel: 'sms'
  }
}
```

### New Event: `sms_outbound`
```javascript
{
  event: 'sms_outbound',
  properties: {
    message_uuid: 'uuid',
    thread_id: 'phone_number',
    from: '+1987654321',
    to: '+1234567890',
    body: 'message content',
    twilio_sid: 'SM...',
    segments: 1,
    timestamp: '2026-01-20T...',
    channel: 'sms',
    message_type: 'chat_response' | 'welcome' | 'notification'
  }
}
```

### New Event: `sms_cost_update`
```javascript
{
  event: 'sms_cost_update',
  properties: {
    message_uuid: 'uuid',
    twilio_sid: 'SM...',
    price: -0.0079,
    price_unit: 'USD',
    status: 'delivered',
    segments: 1,
    direction: 'inbound' | 'outbound'
  }
}
```

### Updated Event: `$ai_generation` (existing PostHog event)
Now includes:
```javascript
{
  // ... existing PostHog LLM properties ...
  message_uuid: 'uuid',           // NEW
  cost_usd: 0.0123,               // NEW (calculated)
  input_tokens: 450,              // already tracked
  output_tokens: 200,             // already tracked
  model: 'gpt-4o'                 // already tracked
}
```

## Migration Notes

### Existing Data
- Existing messages in chat-messages table already have `messageId` (UUID)
- No migration needed for existing data
- New cost fields will only be present on new messages
- GSI will index existing messageIds automatically

### Backward Compatibility
- All changes are additive (no breaking changes)
- Existing queries continue to work
- New GSI is optional for new query patterns
- Cost fields are optional (can be null/missing)

## Testing Checklist

- [ ] Test GPT cost calculation for gpt-4o
- [ ] Test GPT cost calculation for gpt-4o-mini
- [ ] Test SMS cost tracking for outbound messages
- [ ] Test SMS cost tracking for inbound messages
- [ ] Test welcome message logging
- [ ] Test notification message logging
- [ ] Test PostHog events include messageId
- [ ] Test GSI lookup by messageId
- [ ] Test Twilio callback webhook
- [ ] Test cost update for delayed Twilio callbacks
- [ ] Verify costs in DynamoDB match PostHog
- [ ] Test with multi-segment SMS messages

## Deployment Steps

1. **Terraform Changes** (deploy first)
   - Add GSI to chat-messages table
   - Add Twilio callback Lambda and API route
   - Apply: `terraform apply`

2. **Lambda Deployments**
   - Deploy shared message_logger.py (in layer)
   - Deploy updated chat_handler.py
   - Deploy updated agent_service.py
   - Deploy updated sms_handler.py
   - Deploy new twilio_callback_handler.py
   - Deploy updated sms_notifications.py

3. **Verification**
   - Send test SMS inbound
   - Send test SMS outbound
   - Verify DynamoDB costs populated
   - Verify PostHog events include costs
   - Check CloudWatch logs for any errors

## Cost Analysis Queries

### PostHog Queries

**Total GPT costs by day**:
```
Event: $ai_generation
Filter: environment = 'prod'
Aggregate: sum(cost_usd)
Group by: date
```

**Total SMS costs by day**:
```
Event: sms_cost_update
Filter: environment = 'prod'
Aggregate: sum(price)
Group by: date
```

**Cost per user**:
```
Event: $ai_generation OR sms_cost_update
Filter: environment = 'prod'
Aggregate: sum(cost_usd OR price)
Group by: distinct_id
```

### DynamoDB Queries

**Get all costs for a thread**:
```python
response = messages_table.query(
    KeyConditionExpression='threadId = :tid',
    ExpressionAttributeValues={':tid': thread_id}
)

total_gpt_cost = sum(
    msg.get('costs', {}).get('gpt', {}).get('costUsd', 0) 
    for msg in response['Items']
)

total_sms_cost = sum(
    msg.get('costs', {}).get('twilio', {}).get('price', 0)
    for msg in response['Items']
)
```

**Look up message by UUID**:
```python
response = messages_table.query(
    IndexName='MessageUuidIndex',
    KeyConditionExpression='messageId = :uuid',
    ExpressionAttributeValues={':uuid': message_uuid}
)
```

## Future Enhancements

1. **Cost Alerts**
   - Alert when user's daily cost exceeds threshold
   - Alert on unusual cost spikes

2. **Cost Dashboard**
   - Real-time cost tracking dashboard
   - Cost breakdown by user, channel, time period

3. **Budget Management**
   - Set per-user cost limits
   - Throttle expensive operations

4. **Cost Optimization**
   - Detect expensive conversations
   - Suggest model downgrade for simple queries
   - Cache common responses

## References

- [OpenAI Pricing](https://platform.openai.com/docs/pricing)
- [Twilio Message Resource](https://www.twilio.com/docs/messaging/api/message-resource)
- [Twilio Status Callbacks](https://www.twilio.com/docs/messaging/tutorials/how-to-receive-and-reply/python#configure-your-webhook-url)
- [PostHog LLM Analytics](https://posthog.com/docs/llm-analytics)
- [DynamoDB GSI Best Practices](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/GSI.html)

