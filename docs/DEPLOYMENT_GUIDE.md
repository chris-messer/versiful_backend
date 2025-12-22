# LangChain Chat Agent - Deployment Guide

## Quick Start

This guide will help you deploy the new LangChain-based chat agent to your environment.

## Prerequisites

1. **OpenAI API Key**: Ensure your Secrets Manager has a `gpt` or `openai_api_key` field
2. **Python 3.11**: Required for Lambda runtime
3. **Terraform**: For infrastructure deployment
4. **Node.js**: For frontend build

## Deployment Steps

### 1. Backend Deployment

```bash
cd /Users/christopher.messer/PycharmProjects/versiful-backend

# Build the LangChain layer (this will take a few minutes)
cd lambdas/layers/langchain
rm -rf python
mkdir python
pip install -r requirements.txt -t python --platform manylinux2014_x86_64 --only-binary=:all: --python-version 3.11
zip -r layer.zip python
cd ../../..

# Deploy infrastructure
cd terraform
./scripts/tf-env.sh dev plan
./scripts/tf-env.sh dev apply
```

### 2. Frontend Deployment

```bash
cd /Users/christopher.messer/WebstormProjects/versiful-frontend

# Install dependencies (if needed)
npm install

# Build
npm run build

# Deploy (your deployment method)
# e.g., aws s3 sync dist/ s3://your-bucket/
```

## What's New

### Backend Changes

1. **New Lambda Functions**
   - `dev-versiful-chat` - Core chat handler
   - `dev-versiful-web-chat` - Web API handler

2. **Updated Lambda**
   - `dev-versiful-sms_function` - Now invokes chat handler

3. **New DynamoDB Tables**
   - `dev-versiful-chat-messages` - Message history
   - `dev-versiful-chat-sessions` - Session metadata

4. **New Lambda Layer**
   - `dev-langchain-dependencies` - LangChain/LangGraph packages

5. **New API Endpoints**
   - `POST /chat/message`
   - `GET /chat/sessions`
   - `POST /chat/sessions`
   - `GET /chat/sessions/{sessionId}`
   - `DELETE /chat/sessions/{sessionId}`

### Frontend Changes

1. **New Page**
   - `/chat` - Chat interface

2. **Updated Navigation**
   - Added "Chat" link for logged-in users

## Configuration

### Agent Settings

Edit `lambdas/chat/agent_config.yaml` to customize:

```yaml
llm:
  model: "gpt-4o"          # Change model
  temperature: 0.7          # Adjust creativity
  max_tokens: 500           # Response length
  
system_prompt: |
  # Edit the system prompt

guardrails:
  sensitive_topics: [...]   # Add keywords
  crisis_response: |
    # Customize crisis message
```

After editing, redeploy the Chat Lambda:

```bash
cd terraform
./scripts/tf-env.sh dev apply -target=module.lambdas.aws_lambda_function.chat_function
```

## Testing

### 1. Test Web Chat API

```bash
# Run the test script
./scripts/test-chat.sh dev
```

You'll need to provide auth tokens from your browser cookies.

### 2. Test SMS Flow

Send an SMS to your Twilio number:
```
"I'm feeling worried about my future"
```

You should receive a biblical guidance response.

### 3. Test Frontend

1. Navigate to `https://dev.versiful.io/chat`
2. Login if needed
3. Click "New Conversation"
4. Send a message
5. Verify response appears
6. Check that session appears in sidebar

## Monitoring

### CloudWatch Logs

Check these log groups:
- `/aws/lambda/dev-versiful-chat` - Core chat logic
- `/aws/lambda/dev-versiful-web-chat` - API endpoints
- `/aws/lambda/dev-sms_function` - SMS gateway

### DynamoDB

Check tables:
- `dev-versiful-chat-messages` - Message entries
- `dev-versiful-chat-sessions` - Session entries

### Common Errors

**"Chat handler error"**
- Check OpenAI API key in Secrets Manager
- Verify Lambda timeout (60s for chat)
- Check CloudWatch logs

**"Session not found"**
- Verify JWT token is valid
- Check session exists in DynamoDB

**SMS not responding**
- Check usage limits
- Verify CHAT_FUNCTION_NAME env var
- Check Lambda invoke permissions

## Rollback

If you need to rollback:

```bash
# Revert backend changes
cd terraform
git revert <commit-hash>
./scripts/tf-env.sh dev apply

# Revert frontend
cd frontend
git revert <commit-hash>
npm run build && deploy
```

## Cost Estimate

For 1000 users with 10 messages/user/month:

- **Lambda**: ~$5/month (chat processing)
- **DynamoDB**: ~$2/month (message storage)
- **OpenAI API**: ~$100/month (GPT-4o calls)
- **Data Transfer**: ~$1/month

**Total**: ~$108/month

Scale linearly with usage.

## Performance

### Expected Latency

- SMS response: 2-5 seconds
- Web chat response: 2-5 seconds
- Session list: <500ms
- Message history: <1s

### Optimization Tips

1. **Use Provisioned Concurrency** for chat Lambda (reduces cold starts)
2. **Enable DynamoDB Auto Scaling** if traffic is spiky
3. **Cache session data** in Lambda memory
4. **Use GPT-3.5-turbo** for lower cost (sacrifice some quality)

## Security

### Checklist

- [x] JWT authentication on all web endpoints
- [x] CORS configured with specific origins
- [x] Secrets in AWS Secrets Manager
- [x] IAM least privilege permissions
- [x] DynamoDB encryption at rest (default)
- [x] Lambda in VPC (optional, not implemented)

### Hardening (Optional)

1. Enable WAF on API Gateway
2. Add rate limiting per user
3. Enable CloudTrail logging
4. Set up GuardDuty

## Troubleshooting

### Chat Lambda Timeout

Increase timeout:
```hcl
# In _chat.tf
timeout = 90  # Increase from 60
```

### Layer Too Large

The LangChain layer is ~50MB compressed. If it exceeds 250MB uncompressed:

1. Remove unused dependencies
2. Use `--only-binary=:all:` flag
3. Split into multiple layers

### DynamoDB Throttling

Enable auto-scaling:
```hcl
# Add to _chat_tables.tf
billing_mode = "PROVISIONED"
read_capacity  = 5
write_capacity = 5

autoscaling_enabled = true
```

## Support

For issues:
1. Check CloudWatch logs
2. Review this guide
3. Check `docs/LANGCHAIN_CHAT_IMPLEMENTATION.md`
4. Review architecture: `docs/CHAT_ARCHITECTURE.md`

## Next Steps

After successful deployment:

1. **Test thoroughly** using `scripts/test-chat.sh`
2. **Monitor costs** in AWS Cost Explorer
3. **Collect user feedback** on responses
4. **Fine-tune prompts** in `agent_config.yaml`
5. **Add analytics** (conversation length, topics, etc.)
6. **Consider A/B testing** different prompts

## Staging/Production

To deploy to staging/prod:

```bash
# Backend
cd terraform
./scripts/tf-env.sh staging plan
./scripts/tf-env.sh staging apply

# Frontend
# Update .env.staging / .env.production
npm run build -- --mode staging
# Deploy to staging environment
```

Remember to update:
- CORS origins
- Secrets Manager (different keys per env)
- Domain names
- Rate limits (higher for prod)

