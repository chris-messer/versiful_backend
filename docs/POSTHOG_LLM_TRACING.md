# PostHog LLM Analytics Integration

## Overview

PostHog LLM analytics has been integrated into the Versiful chat system to track and analyze all LLM interactions across web chat, SMS, and AI title generation. The integration follows the [official PostHog LangChain documentation](https://posthog.com/docs/llm-analytics/installation/langchain) exactly.

## Implementation Details

### Dependencies

- **PostHog Python SDK**: `posthog==7.5.1`
- **LangChain**: `langchain`, `langchain-core`, `langchain-openai`
- Added to `lambdas/layers/langchain/requirements.txt`

### Session and Trace ID Strategy

PostHog uses the following identifiers to organize LLM traces:

| Context | `$ai_trace_id` | `$ai_session_id` | `distinct_id` |
|---------|---------------|------------------|---------------|
| **Web Chat** | UUID per message (groups chat + title LLM calls) | `thread_id` (userId#sessionId) | `user_id` |
| **SMS Chat** | UUID per message (groups chat + title LLM calls) | Phone number (digits only) | Phone number (digits only) or `user_id` if available |
| **Title Generation** | Same as parent message (grouped with chat) | `thread_id` (of conversation being summarized) | `user_id` or `thread_id` |

**Important**: 
- `$ai_trace_id` is generated **once per user message** (UUID) and shared by all LLM calls handling that message
- This groups the chat generation and title generation LLM calls together under one trace
- `$ai_session_id` groups all messages (traces) within a conversation
- Each message creates one trace containing multiple spans (automatically managed by PostHog LangChain SDK)
- The PostHog SDK automatically creates the trace hierarchy based on LangChain component nesting

### Key Features

1. **Automatic Event Capture**: Every LLM call automatically captures:
   - `$ai_model`: Model used (e.g., `gpt-4o`, `gpt-4o-mini`)
   - `$ai_latency`: Response time in seconds
   - `$ai_input_tokens`: Number of input tokens
   - `$ai_output_tokens`: Number of output tokens
   - `$ai_total_cost_usd`: Estimated cost
   - `$ai_input`: Messages sent to LLM
   - `$ai_output_choices`: LLM responses
   - `$ai_tools`: Available tools/functions
   - `$ai_trace_id`: Unique ID per message
   - `$ai_session_id`: Session ID for conversation grouping
   - `$ai_span_id`: Auto-generated span ID
   - `$ai_span_name`: Auto-generated span name (e.g., "ChatOpenAI", "RunnableSequence")
   - `$ai_parent_id`: Auto-generated parent span reference
   - Custom properties: `channel`, `conversation_id`, `thread_id`, `operation`

2. **Channel-Specific Tracking**:
   - Web chat sessions are grouped by `thread_id` (format: `userId#sessionId`)
   - SMS conversations are grouped by phone number (digits only, symbols stripped)
   - Title generation calls are linked to the conversations they summarize

3. **Automatic Trace Hierarchy**: The PostHog LangChain SDK automatically creates a trace hierarchy based on how LangChain components are nested:
   - LangChain chains create parent spans
   - LLM calls create child generation spans
   - Tool calls are automatically tracked as part of the generation
   - All related operations share the same `$ai_trace_id`

4. **Official PostHog Pattern**: Implementation follows the [official docs](https://posthog.com/docs/llm-analytics/installation/langchain) exactly:
   ```python
   callback_handler = CallbackHandler(
       client=posthog,
       distinct_id="user_id",
       trace_id="uuid_per_message",
       properties={
           "$ai_session_id": "session_id",  # For grouping traces into sessions
           "conversation_id": "thread_id",   # Custom property
           "channel": "web"                   # Custom property
       },
       privacy_mode=False
   )
   
   # Pass to LangChain invoke
   response = llm.invoke(messages, config={"callbacks": [callback_handler]})
   ```

## Modified Files

### Backend Code

1. **`lambdas/layers/langchain/requirements.txt`**
   - Added `posthog==7.5.1`

2. **`lambdas/chat/agent_service.py`**
   - Added PostHog imports: `from posthog import Posthog` and `from posthog.ai.langchain import CallbackHandler`
   - Updated `__init__` to accept `posthog_api_key` parameter
   - Added PostHog client initialization
   - Created `_create_posthog_callback()` method to generate callback handlers with proper session/trace IDs
   - Updated `_generate_llm_response()` to accept `thread_id`, `phone_number`, `user_id` and use PostHog callbacks
   - Updated `process_message()` to accept `phone_number` parameter
   - Updated `get_conversation_title()` to accept `thread_id`, `user_id` and use PostHog tracing
   - Updated `get_agent_service()` factory to accept `posthog_api_key`

3. **`lambdas/chat/chat_handler.py`**
   - Updated `get_agent()` to retrieve PostHog API key from environment or secrets
   - Updated call to `agent.process_message()` to pass `phone_number`
   - Updated call to `agent.get_conversation_title()` to pass `thread_id` and `user_id`

4. **`lambdas/chat/web_handler.py`**
   - Updated `generate_ai_title()` to accept `thread_id` and `user_id` parameters
   - Updated calls to `generate_ai_title()` in `handle_post_message()` and `handle_update_session_title()` to pass these parameters

### Terraform Infrastructure

1. **`terraform/modules/lambdas/variables.tf`**
   - Added `posthog_apikey` variable

2. **`terraform/modules/lambdas/_chat.tf`**
   - Added `POSTHOG_API_KEY` environment variable to `chat_function`
   - Added `POSTHOG_API_KEY` environment variable to `web_chat_function`

3. **`terraform/main.tf`**
   - Added `posthog_apikey = var.posthog_apikey` to `lambdas` module call

4. **`terraform/dev.tfvars`**
   - Already contains: `posthog_apikey = "phc_9TcKpbVhdwIyOv8NjEjr8UnKNaK6bKeiOBBrJoi2wEG"`

## Usage

### Viewing Traces in PostHog

1. Navigate to PostHog dashboard: https://us.i.posthog.com
2. Go to **LLM analytics** → **Generations** to see all LLM calls
3. Go to **LLM analytics** → **Traces** to see grouped conversation traces
4. Filter by:
   - `channel` property: "web" or "sms"
   - `$ai_session_id`: Specific conversation thread
   - `$ai_span_name`: "chat_generation" or "title_generation"
   - `distinct_id`: Specific user

### Example Trace Hierarchy

```
Session: 15551234567 (SMS user - phone digits only)
├── Trace: abc123-uuid (Message 1: "How do I pray?")
│   ├── Span: chat_generation (gpt-4o)
│   │   └── Tool Call: get_versiful_info
│   └── Span: title_generation (gpt-4o-mini) → "Prayer Guidance"
├── Trace: def456-uuid (Message 2: "Tell me more")
│   └── Span: chat_generation (gpt-4o)
└── Trace: ghi789-uuid (Message 3: "Thank you")
    └── Span: chat_generation (gpt-4o)

Session: user123#sess456 (Web user)
├── Trace: xyz111-uuid (Message 1: "What does John 3:16 mean?")
│   ├── Span: chat_generation (gpt-4o)
│   └── Span: title_generation (gpt-4o-mini) → "Understanding John 3:16"
├── Trace: xyz222-uuid (Message 2: "Can you explain more?")
│   └── Span: chat_generation (gpt-4o)
└── Trace: xyz333-uuid (Message 3: "That helps, thanks!")
    └── Span: chat_generation (gpt-4o)
```

**Key Points**:
- Each user message creates **one trace** (UUID generated at start of message handling)
- All LLM calls for that message (chat generation, title generation, tool calls) share the **same trace ID**
- This groups related LLM operations together under one trace
- Multiple traces in the same conversation share the **same session ID**
- This allows you to analyze individual messages while still grouping them by conversation

## Cost Tracking

PostHog automatically calculates and displays:
- Token usage (input/output)
- Estimated costs in USD based on model pricing
- Average latency per model
- Total API usage over time

## Monitoring

### CloudWatch Logs

Search for these log messages to verify PostHog integration:
- `"PostHog initialized successfully"` - Confirms PostHog client is working
- `"Created PostHog callback"` - Shows callback handler creation with session/trace IDs
- `"Generated conversation title"` - Title generation events

### PostHog Events

All LLM calls generate `$ai_generation` events with full metadata. Check for:
- Consistent `$ai_session_id` across related conversations
- Proper `$ai_trace_id` matching thread IDs
- `channel` property correctly set to "web" or "sms"

## Troubleshooting

### PostHog Not Capturing Events

1. Check Lambda environment variables: `POSTHOG_API_KEY` should be set
2. Check CloudWatch logs for PostHog initialization errors
3. Verify API key is valid in PostHog project settings
4. Ensure Lambda has internet access to reach `https://us.i.posthog.com`

### Missing Session/Trace Grouping

1. Verify `thread_id` is consistent across messages in same conversation
2. Check that `phone_number` is being passed for SMS calls
3. Ensure `user_id` is available for web chat calls

### High Latency

PostHog callbacks run asynchronously and should not add significant latency. If experiencing issues:
1. Check PostHog client initialization is reused across Lambda invocations
2. Verify no synchronous blocking on PostHog API calls
3. Consider privacy_mode if sending large message content

## Future Enhancements

1. **Custom Metrics**: Add custom properties for:
   - Bible version preference
   - User plan tier (free/paid)
   - Crisis intervention triggers
   - Tool usage patterns

2. **User Feedback**: Integrate user ratings/feedback with LLM traces

3. **A/B Testing**: Use PostHog feature flags to test different prompts or models

4. **Cost Alerts**: Set up PostHog alerts for unusual cost spikes

5. **Quality Monitoring**: Track generation quality metrics (response length, coherence, etc.)
