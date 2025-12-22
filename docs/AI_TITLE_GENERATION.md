# AI-Powered Conversation Title Generation

## Overview

The chat system now uses GPT-4o-mini to automatically generate intelligent, concise titles for conversations instead of simply using the first message.

## How It Works

### 1. Initial Title (First Message)
When a user sends their first message:
- A simple title is generated from the first user message (first sentence, max 50 chars)
- This provides immediate context without extra API calls

### 2. AI Title Generation (After 3+ Messages)
After the conversation has 3 or more messages:
- The system automatically generates an AI-powered title using GPT-4o-mini
- The title summarizes the conversation theme in 4-6 words
- This happens automatically on the 4th message exchange

### 3. Manual Regeneration (Optional)
Users or admins can manually trigger title regeneration:
- Endpoint: `PUT /chat/sessions/{sessionId}/title`
- Uses GPT-4o-mini to analyze conversation and generate a new title

## Implementation Details

### Backend Changes

#### `agent_service.py`
```python
# New LLM instance for title generation
self.title_llm = ChatOpenAI(
    model='gpt-4o-mini',
    temperature=0.5,
    max_tokens=50
)

def get_conversation_title(self, messages: List[Dict[str, str]]) -> str:
    """
    Generate a concise title using GPT-4o-mini
    - Analyzes up to 10 messages
    - Generates 4-6 word title
    - Max 50 characters
    """
```

#### `web_handler.py`
```python
def generate_ai_title(messages: List[Dict[str, Any]]) -> str:
    """Generate an AI-powered title using GPT-4o-mini"""
    agent = get_agent()
    return agent.get_conversation_title(messages)

def handle_post_message(event, user_id):
    """
    Enhanced message handler:
    - First message: Simple title from user input
    - After 3+ messages: Auto-generate AI title
    """
    
def handle_update_session_title(event, user_id):
    """
    New endpoint: PUT /chat/sessions/{sessionId}/title
    Manually regenerate title using AI
    """
```

### API Gateway Routes

New route added to Terraform:
```hcl
resource "aws_apigatewayv2_route" "chat_session_title_update_route" {
  api_id             = var.apiGateway_lambda_api_id
  route_key          = "PUT /chat/sessions/{sessionId}/title"
  target             = "integrations/${aws_apigatewayv2_integration.chat_session_title_update_integration.id}"
  authorization_type = "CUSTOM"
  authorizer_id      = var.jwt_auth_id
}
```

## API Usage

### Automatic Title Generation
No action needed - titles are automatically generated:
1. First message: Simple title created
2. 4th message: AI title automatically generated and updated

### Manual Title Regeneration
```bash
PUT /chat/sessions/{sessionId}/title
Authorization: Bearer <token>

Response:
{
  "title": "Prayer for Strength",
  "message": "Title updated successfully"
}
```

## Benefits

1. **Cost-Effective**: Uses GPT-4o-mini (~$0.15 per 1M tokens) instead of GPT-4
2. **Better UX**: Titles are descriptive and meaningful, not just truncated first messages
3. **Automatic**: Happens in the background without user intervention
4. **Flexible**: Can be manually triggered if needed

## Examples

### Before (Simple Title)
- "Hey, I'm feeling anxious about my..."
- "Can you help me understand James..."
- "I've been struggling with forgi..."

### After (AI-Generated)
- "Anxiety and Faith"
- "Understanding James 2:14"
- "Journey to Forgiveness"

## Deployment

1. Deploy updated Lambda functions:
   ```bash
   cd terraform
   terraform apply
   ```

2. The feature will automatically activate for:
   - All new conversations
   - Existing conversations when they receive new messages

## Monitoring

Monitor title generation in CloudWatch logs:
- Search for: `"Generated conversation title"`
- Track AI title generation success/failures
- Monitor GPT-4o-mini API costs

## Future Enhancements

1. **User Customization**: Allow users to edit titles manually
2. **Language Detection**: Generate titles in user's preferred language
3. **Emoji Support**: Add relevant emojis to titles for visual appeal
4. **Category Tags**: Auto-tag conversations by topic (prayer, scripture, guidance)

