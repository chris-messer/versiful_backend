# LangChain Chat Agent - Implementation Summary

## Overview
This implementation adds a sophisticated LangChain/LangGraph-based chat agent to Versiful that supports both SMS and web interfaces with conversation history, guardrails, and configurable prompts.

## Architecture

### Core Components

1. **Agent Service** (`lambdas/chat/agent_service.py`)
   - LangGraph-based conversation flow
   - Guardrails for crisis detection and content filtering
   - Channel-aware response formatting (SMS vs Web)
   - Configurable via YAML file

2. **Chat Handler** (`lambdas/chat/chat_handler.py`)
   - Channel-agnostic message processing
   - DynamoDB message history management
   - Direct Lambda invocation interface

3. **Web Handler** (`lambdas/chat/web_handler.py`)
   - REST API for web chat
   - Session management
   - JWT-authenticated endpoints

4. **SMS Handler** (Updated `lambdas/sms/sms_handler.py`)
   - Thin wrapper that invokes Chat Handler
   - Maintains existing usage tracking

### DynamoDB Tables

#### chat-messages
- **PK**: threadId (phone number for SMS, userId#sessionId for web)
- **SK**: timestamp
- **Attributes**: role, content, channel, userId, phoneNumber, metadata
- **GSI**: UserMessagesIndex, ChannelMessagesIndex

#### chat-sessions
- **PK**: userId
- **SK**: sessionId
- **Attributes**: threadId, title, messageCount, lastMessageAt
- **GSI**: SessionsByLastMessageIndex

### Lambda Layers

#### langchain Layer
Contains:
- langchain==0.3.13
- langgraph==0.2.53
- langchain-openai==0.2.13
- langchain-community==0.3.13
- pydantic==2.10.6

Used by: Chat Lambda

### API Endpoints

#### Web Chat API (JWT Protected)
- `POST /chat/message` - Send message, get response
- `GET /chat/sessions` - List user's sessions
- `POST /chat/sessions` - Create new session
- `GET /chat/sessions/{sessionId}` - Get session with messages
- `DELETE /chat/sessions/{sessionId}` - Archive session

## Configuration

### Agent Configuration (`lambdas/chat/agent_config.yaml`)

```yaml
llm:
  provider: "openai"
  model: "gpt-4o"
  temperature: 0.7
  max_tokens: 500
  sms:
    max_tokens: 300  # Shorter for SMS

system_prompt: |
  [Compassionate biblical guide prompt]

sms_system_prompt: |
  [Concise SMS-specific prompt]

history:
  max_messages: 20
  context_window: 10

guardrails:
  sensitive_topics: [suicide, self-harm, abuse, violence]
  crisis_response: |
    [Crisis intervention message with hotline numbers]
  filter_profanity: true
```

## Thread ID Strategy

### SMS
- `threadId` = E.164 phone number (e.g., `+12345678901`)
- Single continuous conversation per phone
- History persists across messages

### Web
- `threadId` = `{userId}#{sessionId}` (e.g., `user-123#abc-def`)
- Multiple sessions per user
- Each session is independent

## Deployment

### Terraform Resources

New resources in `terraform/modules/lambdas/`:
- `_chat_tables.tf` - DynamoDB tables
- `_chat.tf` - Lambda functions and API Gateway routes
- Updated `_layers.tf` - LangChain layer
- Updated `main.tf` - IAM policies for chat tables and Lambda invoke

### Environment Variables

#### Chat Lambda
- `CHAT_MESSAGES_TABLE`
- `CHAT_SESSIONS_TABLE`

#### Web Chat Lambda
- `CHAT_MESSAGES_TABLE`
- `CHAT_SESSIONS_TABLE`
- `CHAT_FUNCTION_NAME`
- `CORS_ORIGIN`

#### SMS Lambda (Updated)
- `CHAT_FUNCTION_NAME` (new)

## Testing

### Unit Tests (to be added)
```bash
# Test agent service
pytest tests/unit/test_agent_service.py

# Test chat handler
pytest tests/unit/test_chat_handler.py

# Test web handler
pytest tests/unit/test_web_handler.py
```

### Integration Tests (to be added)
```bash
# Test SMS to Chat flow
pytest tests/integration/test_sms_chat_integration.py

# Test Web Chat API
pytest tests/integration/test_web_chat_api.py
```

### Manual Testing

#### SMS Flow
1. Send SMS to Twilio number
2. Check CloudWatch logs for SMS Lambda → Chat Lambda invocation
3. Verify response received via SMS
4. Check DynamoDB for message history with threadId = phone number

#### Web Flow
1. Login to web app
2. Navigate to `/chat`
3. Start new conversation
4. Send message
5. Verify response appears
6. Check session appears in sidebar
7. Verify message history persists on refresh

### Testing Checklist

- [ ] SMS message triggers chat response
- [ ] SMS response under 1500 chars
- [ ] Web chat sends/receives messages
- [ ] Multiple sessions work independently
- [ ] Session list updates in real-time
- [ ] Message history loads correctly
- [ ] Crisis keywords trigger intervention message
- [ ] Rate limiting works
- [ ] Conversation history maintained (last N messages)
- [ ] Session deletion works
- [ ] CORS configured correctly
- [ ] JWT authentication enforced

## Frontend

### New Pages
- `src/pages/Chat.jsx` - Main chat interface

### Features
- ✅ Real-time messaging
- ✅ Session management (create, list, delete)
- ✅ Message history
- ✅ Auto-scroll to latest message
- ✅ Loading states
- ✅ Responsive design (desktop/mobile)
- ✅ Dark mode support

## Migration Notes

### From Old to New
1. Old `generate_response()` function in `sms/helpers.py` is now replaced
2. SMS still maintains usage tracking (unchanged)
3. Message history now persisted (new feature)
4. Guardrails now enforced (new feature)

### Backward Compatibility
- Existing SMS flow unchanged from user perspective
- Usage tracking and limits still enforced
- Phone number normalization unchanged

## Configuration Changes

### Easy to Modify
- Prompts: Edit `agent_config.yaml`
- Model: Change `llm.model` in YAML
- Temperature: Change `llm.temperature` in YAML
- Guardrails: Edit `guardrails` section in YAML

### Requires Deployment
- Adding new Lambda endpoints
- Changing DynamoDB table structure
- Updating IAM permissions

## Performance Considerations

### Lambda Timeouts
- Chat Lambda: 60s (for LLM calls)
- Web Chat Lambda: 30s
- SMS Lambda: 30s (unchanged)

### Memory
- Chat Lambda: 512MB (for LangChain/LangGraph)
- Web Chat Lambda: 256MB
- SMS Lambda: 128MB (unchanged)

### Cold Starts
- LangChain layer adds ~2-3s to cold start
- Container reuse keeps warm start under 500ms
- Consider Provisioned Concurrency for production

## Cost Considerations

### DynamoDB
- Pay-per-request billing
- Estimated: $0.25 per million reads/writes
- GSIs incur additional costs

### Lambda
- Chat Lambda: ~$0.20 per million requests (512MB, 5s avg)
- Web Chat Lambda: ~$0.10 per million requests (256MB, 2s avg)

### OpenAI API
- GPT-4o: ~$0.01 per message (varies by length)
- Monitor via CloudWatch metrics

## Monitoring

### CloudWatch Metrics
- Lambda invocations/errors/duration
- DynamoDB read/write capacity
- API Gateway 4xx/5xx errors

### CloudWatch Logs
- Agent decisions (crisis, off-topic, normal)
- Message counts per thread
- LLM response times

### Alarms to Set
- Chat Lambda error rate > 5%
- DynamoDB throttling
- OpenAI API errors
- Average response time > 10s

## Future Enhancements

### Phase 2
- [ ] Message summarization for long conversations
- [ ] RAG with biblical knowledge base
- [ ] Multi-language support
- [ ] Voice message transcription
- [ ] Image attachment support

### Phase 3
- [ ] A/B testing different prompts
- [ ] Conversation analytics dashboard
- [ ] User feedback on responses
- [ ] Advanced guardrails (toxicity detection)
- [ ] Conversation export

## Support

### Common Issues

#### "Chat handler error"
- Check OpenAI API key in Secrets Manager
- Verify Lambda has permission to invoke Chat Lambda
- Check CloudWatch logs for stack traces

#### "Session not found"
- Session may have been deleted
- Check DynamoDB for session existence
- Verify JWT token has correct userId

#### SMS not responding
- Check usage limits not exceeded
- Verify Twilio webhook configured
- Check SMS Lambda has CHAT_FUNCTION_NAME env var

#### Messages not persisting
- Verify DynamoDB tables exist
- Check IAM permissions for chat tables
- Verify threadId format correct

## Documentation
- Architecture: `docs/CHAT_ARCHITECTURE.md`
- API Reference: (to be added)
- Agent Configuration: `lambdas/chat/agent_config.yaml`

