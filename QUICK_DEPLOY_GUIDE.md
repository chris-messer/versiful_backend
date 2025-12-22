# Quick Reference: AI Conversation Titles

## What Changed
✅ Chat UI completely rebuilt (mobile-friendly, modern design)
✅ Conversation titles now use GPT-4o-mini to generate smart, concise summaries
✅ Titles auto-generate after 3+ message exchanges
✅ New API endpoint for manual title regeneration

## Key Features

### Automatic Title Generation
- **1st message**: Simple title (first sentence)
- **4th message**: AI-generated title (4-6 words, descriptive)
- **Cost**: < $0.001 per title
- **No user action needed**

### Manual Regeneration
```bash
PUT /chat/sessions/{sessionId}/title
Authorization: Bearer <token>
```

## Deploy Commands

```bash
# Backend
cd /Users/christopher.messer/PycharmProjects/versiful-backend/terraform
terraform apply -var-file=dev.tfvars

# Frontend - already deployed, no action needed
```

## Test It

```bash
# Test title generation locally
cd /Users/christopher.messer/PycharmProjects/versiful-backend
export OPENAI_API_KEY=your-key
python3 test_title_generation.py
```

## Monitor

```bash
# Watch for title generation in logs
aws logs tail /aws/lambda/dev-versiful-web-chat --follow | grep "Generated conversation title"
```

## Files Modified
1. `versiful-frontend/src/pages/Chat.jsx` - UI rebuild
2. `versiful-backend/lambdas/chat/agent_service.py` - AI logic
3. `versiful-backend/lambdas/chat/web_handler.py` - Title endpoint
4. `versiful-backend/terraform/modules/lambdas/_chat.tf` - API route

## Examples
- "I'm anxious about..." → **"Anxiety and Faith"**
- "Help me understand James..." → **"Understanding James 2:14"**
- "How do I forgive..." → **"Journey to Forgiveness"**

## Status
✅ Ready to deploy
✅ Zero breaking changes
✅ Backwards compatible

