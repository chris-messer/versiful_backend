# Chat Architecture - LangChain/LangGraph Integration

## Overview
This document describes the architecture for the unified chat agent system that handles both SMS and web chat interfaces using LangChain/LangGraph.

## DynamoDB Tables

### 1. Chat Messages Table
**Table Name**: `{environment}-{project}-chat-messages`

**Purpose**: Store all chat messages for both SMS and web interfaces

**Schema**:
```
Partition Key: threadId (String)  - E.164 phone number for SMS, userId#sessionId for web
Sort Key: timestamp (String)       - ISO 8601 timestamp
```

**Attributes**:
- `threadId` (String) - Unique identifier for the conversation thread
- `timestamp` (String) - ISO 8601 timestamp with milliseconds
- `messageId` (String) - Unique message identifier (UUID)
- `role` (String) - "user" or "assistant"
- `content` (String) - Message content
- `channel` (String) - "sms" or "web"
- `userId` (String, optional) - Cognito user ID if authenticated
- `phoneNumber` (String, optional) - E.164 phone number for SMS
- `metadata` (Map, optional) - Additional metadata (model used, tokens, etc.)
- `createdAt` (String) - ISO timestamp
- `updatedAt` (String) - ISO timestamp

**GSI 1**: UserMessages
- Partition Key: `userId`
- Sort Key: `timestamp`
- Purpose: Query all messages for a specific user across all sessions

**GSI 2**: ChannelMessages
- Partition Key: `channel`
- Sort Key: `timestamp`
- Purpose: Analytics and monitoring by channel

### 2. Chat Sessions Table
**Table Name**: `{environment}-{project}-chat-sessions`

**Purpose**: Track chat sessions for web interface (SMS uses phone as implicit session)

**Schema**:
```
Partition Key: userId (String)
Sort Key: sessionId (String) - UUID for each chat session
```

**Attributes**:
- `userId` (String) - Cognito user ID
- `sessionId` (String) - UUID for the session
- `threadId` (String) - Full thread identifier (userId#sessionId)
- `title` (String) - Auto-generated or user-provided title
- `messageCount` (Number) - Total messages in this session
- `lastMessageAt` (String) - ISO timestamp of last message
- `channel` (String) - "web" (SMS doesn't need sessions table)
- `createdAt` (String) - ISO timestamp
- `updatedAt` (String) - ISO timestamp
- `archived` (Boolean) - Whether session is archived

**GSI 1**: SessionsByLastMessage
- Partition Key: `userId`
- Sort Key: `lastMessageAt`
- Purpose: List user's sessions ordered by most recent activity

## Architecture Components

### 1. Agent Service (`lambdas/chat/agent_service.py`)
- Core LangGraph agent logic
- Loads configuration from `agent_config.yaml`
- Implements conversation chain with memory
- Handles guardrails and content filtering
- Channel-aware (SMS vs web) for response formatting

### 2. Chat Lambda (`lambdas/chat/chat_handler.py`)
- Channel-agnostic message handler
- Interfaces with Agent Service
- Manages DynamoDB interactions for message history
- Returns structured responses

### 3. SMS Lambda (Updated)
- Thin wrapper around Chat Lambda
- Handles Twilio webhook parsing
- Maps phone number to threadId
- Sends response via Twilio

### 4. Web Chat Lambda (`lambdas/chat/web_handler.py`)
- REST API for web chat
- Endpoints:
  - `POST /chat/message` - Send message and get response
  - `GET /chat/sessions` - List user's chat sessions
  - `GET /chat/sessions/{sessionId}` - Get session details and messages
  - `POST /chat/sessions` - Create new session
  - `DELETE /chat/sessions/{sessionId}` - Archive session

### 5. LangChain Layer
- Contains: langchain, langgraph, langchain-openai, langchain-community
- Heavy dependencies isolated in layer
- Shared across chat-related lambdas

## Thread ID Strategy

### SMS
- `threadId` = E.164 phone number (e.g., `+12345678901`)
- One continuous conversation per phone number
- No session concept needed

### Web
- `threadId` = `{userId}#{sessionId}` (e.g., `user-123#session-abc`)
- Multiple sessions per user
- Each session is a separate conversation thread
- Allows for "new chat" functionality

## Message Flow

### SMS Flow
```
1. SMS received by Twilio → API Gateway
2. SMS Lambda parses webhook
3. SMS Lambda calls Chat Lambda with:
   - threadId: phone number
   - message: user message
   - channel: "sms"
   - userId: from sms_usage table if available
4. Chat Lambda:
   - Loads last N messages from DynamoDB
   - Calls Agent Service
   - Stores messages (user + assistant)
   - Returns response
5. SMS Lambda sends via Twilio
```

### Web Flow
```
1. Frontend POST /chat/message with:
   - sessionId (or null for new session)
   - message
   - Auth token in cookie
2. Web Chat Lambda:
   - Validates JWT token
   - Creates session if new
   - Constructs threadId
   - Calls Chat Lambda with:
     - threadId: userId#sessionId
     - message: user message
     - channel: "web"
     - userId: from JWT
3. Chat Lambda processes (same as SMS)
4. Web Chat Lambda returns JSON response
5. Frontend displays message
```

## Configuration Management

### agent_config.yaml
- Prompts (system, sms-specific)
- Model selection and parameters
- Guardrails configuration
- Rate limiting rules
- Response formatting rules

**Loading Strategy**:
- Bundled with Lambda deployment
- Loaded at container initialization
- Can be overridden via environment variables
- Future: Store in S3 for hot-reload without redeployment

## Benefits of This Architecture

1. **Decoupled**: Agent logic separated from channel-specific code
2. **Flexible**: Easy to add new channels (WhatsApp, Slack, etc.)
3. **Maintainable**: Single agent configuration for all channels
4. **Scalable**: Lambda + DynamoDB scale independently
5. **Testable**: Agent service can be tested independently
6. **Observable**: Centralized message storage for analytics

## Migration Path

1. Deploy new infrastructure (tables, layer, lambdas)
2. Update SMS Lambda to use new Chat Lambda
3. Test SMS flow in dev
4. Deploy Web Chat API
5. Build frontend chat UI
6. Gradually migrate users
7. Deprecate old `generate_response` function

## Future Enhancements

- Message summarization for long conversations
- Multi-language support
- Voice message transcription
- Image/media attachment support
- Advanced RAG with biblical knowledge base
- A/B testing different prompts/models

