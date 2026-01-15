# PostHog LLM Tracing Implementation

This document describes the PostHog integration for tracking LLM usage across all Versiful chat interactions (SMS and Web).

## Overview

PostHog tracing has been integrated at the Lambda layer to capture all LLM interactions, providing visibility into:
- LLM call metrics (tokens, latency, cost)
- Tool usage
- Agent behavior
- Errors and performance issues
- Channel-specific analytics (SMS vs Web)

## Architecture

### Components

1. **PostHog Tracer Module** (`lambdas/chat/posthog_tracer.py`)
   - LangChain callback handler that captures all LLM events
   - Sends structured events to PostHog
   - Tracks tokens, cost, latency, and errors

2. **Agent Service Integration** (`lambdas/chat/agent_service.py`)
   - Initializes PostHog tracer for each LLM call
   - Passes user context (user_id, channel, thread_id)
   - Flushes traces after completion

3. **Environment Configuration** (Terraform)
   - `POSTHOG_API_KEY` environment variable added to chat and SMS lambdas
   - Environment name (`dev`/`staging`/`prod`) for filtering

## Events Tracked

### Core LLM Events

#### `llm_call_start`
Fired when LLM call begins
```json
{
  "model": "gpt-4o",
  "prompt_count": 1,
  "prompt_lengths": [450],
  "total_prompt_length": 450,
  "prompts": ["User asked: How can I find peace?..."],
  "run_id": "uuid",
  "llm_call_number": 1
}
```

#### `llm_call_end`
Fired when LLM call completes
```json
{
  "model": "gpt-4o",
  "prompt_tokens": 450,
  "completion_tokens": 200,
  "total_tokens": 650,
  "latency_seconds": 2.3,
  "estimated_cost_usd": 0.0085,
  "response_length": 850,
  "response": "Finding peace comes from trusting in God...",
  "generation_count": 1
}
```

#### `llm_error`
Fired on LLM errors
```json
{
  "error_type": "RateLimitError",
  "error_message": "Rate limit exceeded",
  "run_id": "uuid"
}
```

### Tool Events

#### `tool_call_start` / `tool_call_end` / `tool_error`
Tracks when agent uses tools (e.g., `get_versiful_info`)

### Agent Events

#### `agent_action` / `agent_finish`
Tracks agent reasoning and decisions

### Summary Events

#### `trace_complete`
Fired at end of each conversation turn
```json
{
  "llm_calls": 2,
  "tool_calls": 1,
  "total_tokens": 1200
}
```

### Standard Properties

All events include:
```json
{
  "environment": "dev|staging|prod",
  "channel": "sms|web|title_generation",
  "thread_id": "conversation_identifier",
  "trace_id": "unique_trace_id",
  "timestamp": "2026-01-14T12:00:00Z",
  "phone_number": "+11234567890"  // For SMS users
}
```

**User Identification:**
- **SMS users**: `distinct_id` = phone number
- **Web users**: `distinct_id` = user_id

## PostHog Dashboard Setup

### Recommended Insights

#### 1. LLM Usage Overview
**Metric:** Total LLM calls by environment
- Event: `llm_call_end`
- Group by: `environment`
- Visualization: Bar chart

#### 2. Token Usage
**Metric:** Sum of `total_tokens` 
- Event: `llm_call_end`
- Breakdown by: `channel` (SMS vs Web)
- Visualization: Line chart over time

#### 3. Cost Tracking
**Metric:** Sum of `estimated_cost_usd`
- Event: `llm_call_end`
- Group by: `environment`
- Visualization: Line chart with cumulative sum

#### 4. Response Latency
**Metric:** Average `latency_seconds`
- Event: `llm_call_end`
- Percentiles: p50, p95, p99
- Group by: `channel`

#### 5. Error Rate
**Metric:** Count of `llm_error` / Total `llm_call_start`
- Events: `llm_error`, `llm_call_start`
- Visualization: Percentage over time

#### 6. Tool Usage
**Metric:** Count of `tool_call_start`
- Event: `tool_call_start`
- Group by: `tool_name`
- Visualization: Pie chart

#### 7. Channel Comparison
**Funnel:**
1. `llm_call_start` (by channel)
2. `llm_call_end` (by channel)
3. Compare SMS vs Web usage

### Filters

Create saved filters for:
- **Dev Environment**: `environment = 'dev'`
- **Staging Environment**: `environment = 'staging'`
- **Production Environment**: `environment = 'prod'`
- **SMS Only**: `channel = 'sms'`
- **Web Only**: `channel = 'web'`

## Querying Examples

### Total tokens used today (Production only)
```
Event: llm_call_end
Filter: environment = 'prod'
Date range: Today
Aggregate: Sum of total_tokens
```

### Average cost per conversation
```
Event: trace_complete
Filter: environment = 'prod'
Group by: thread_id
Aggregate: Sum of estimated_cost_usd
Then: Average across thread_ids
```

### SMS vs Web token usage comparison
```
Event: llm_call_end
Filter: environment = 'prod'
Breakdown: channel
Aggregate: Sum of total_tokens
Visualization: Stacked bar chart
```

### Error rate by model
```
Event: llm_error
Group by: model
Date range: Last 7 days
```

## Cost Estimates

The tracer estimates costs based on OpenAI pricing:
- **GPT-4o**: $2.50/1M input tokens, $10/1M output tokens
- Estimates are approximate and should be validated against actual billing

## Environment Variables

### Required
- `POSTHOG_API_KEY`: PostHog project API key
- `ENVIRONMENT`: Environment name (dev/staging/prod)

### Optional
- None (user_id, channel, thread_id passed at runtime)

## Deployment

### Lambda Layers
PostHog SDK (`posthog==3.1.0`) is included in the langchain layer:
- `lambdas/layers/langchain/requirements.txt`

### Terraform Configuration
PostHog API key is configured per environment:
- `terraform/dev.tfvars`
- `terraform/staging.tfvars`
- `terraform/prod.tfvars`

Environment variable added to:
- Chat Lambda (`chat_function`)
- Web Chat Lambda (`web_chat_function`)
- SMS Lambda (`sms_function`)

## Performance Considerations

### Overhead
- PostHog events are sent asynchronously
- Minimal impact on response latency (<10ms)
- Events are batched and flushed at end of trace

### Volume
Expected event volume per conversation:
- **Simple response**: 2-4 events (llm_start, llm_end, trace_complete)
- **With tool use**: 6-10 events (includes tool events)
- **With title generation**: +2 events

Daily estimates:
- **Dev**: ~500 events/day
- **Staging**: ~100 events/day  
- **Production**: ~5,000-10,000 events/day

## Privacy & Compliance

### Data Sent to PostHog

✅ **User identifiers**
- User ID (for registered web users)
- Phone numbers (as distinct_id for SMS users)

✅ **Conversation content** (for debugging and analysis)
- User messages/prompts (truncated to 2000 chars)
- LLM responses (truncated to 2000 chars)
- Tool inputs and outputs (truncated to 1000 chars)

✅ **Metrics**
- Token counts
- Response latency
- Cost estimates
- Error types and messages

✅ **Context**
- Channel (SMS/Web)
- Environment (dev/staging/prod)
- Thread/conversation IDs
- Timestamps

### Use Cases

**Debugging**: See exactly what users asked and what the LLM responded with  
**Quality Control**: Review conversations for accuracy and appropriateness  
**Content Analysis**: Understand what topics users care about  
**User Support**: Track specific user interactions for support issues  
**A/B Testing**: Analyze different prompt variations and their responses

### Data Retention

Configure PostHog retention settings to control how long conversation data is kept:
- **Recommended**: 30-90 days for operational analytics
- Can be extended for compliance or historical analysis
- Consider GDPR/privacy requirements for your jurisdiction

## Monitoring & Alerts

### Recommended Alerts

1. **High Error Rate**
   - Condition: `llm_error` count > 10% of `llm_call_start` in 5 minutes
   - Action: Notify engineering team

2. **Latency Spike**
   - Condition: p95 latency > 5 seconds for 10 minutes
   - Action: Investigate OpenAI status

3. **Cost Threshold**
   - Condition: Daily cost estimate > $50 (production)
   - Action: Review usage patterns

4. **Token Usage Spike**
   - Condition: Hourly tokens > 2x average
   - Action: Check for anomalous usage

## Troubleshooting

### Tracer Not Sending Events

**Issue**: No events appearing in PostHog

**Solutions**:
1. Verify `POSTHOG_API_KEY` is set in Lambda environment
2. Check CloudWatch logs for PostHog errors
3. Ensure `posthog` package is in langchain layer
4. Verify Lambda has internet access (NAT gateway)

### Missing Properties

**Issue**: Events missing `environment` or `channel`

**Solutions**:
1. Ensure `ENVIRONMENT` env var is set
2. Check that `channel` is passed to `process_message()`
3. Verify tracer initialization in logs

### High Latency

**Issue**: PostHog causing slow responses

**Solutions**:
1. Check if `flush()` is being called properly
2. Verify PostHog US endpoint is reachable
3. Consider sampling for high-volume scenarios

## Future Enhancements

### Planned Improvements
- [ ] Add conversation quality metrics (user satisfaction)
- [ ] Track Bible version usage distribution
- [ ] Add A/B testing support for prompt variations
- [ ] Cost alerts and budget tracking
- [ ] Real-time dashboard for ops team
- [ ] User segmentation by engagement level

### Advanced Analytics
- Conversation flow analysis
- Topic modeling from token patterns
- Churn prediction based on usage
- Response quality scoring

## References

- [PostHog Python SDK](https://posthog.com/docs/libraries/python)
- [LangChain Callbacks](https://python.langchain.com/docs/modules/callbacks/)
- [OpenAI Pricing](https://openai.com/pricing)

## Support

For questions or issues:
- Check CloudWatch logs: `/aws/lambda/{env}-versiful-chat`
- PostHog dashboard: [https://us.posthog.com](https://us.posthog.com)
- Engineering team: See CICD_DEPLOYMENT_WORKFLOW.md

---

**Last Updated**: 2026-01-14  
**Status**: Implemented, ready for deployment

