# DynamoDB Tables for Chat functionality

# Chat Messages Table
resource "aws_dynamodb_table" "chat_messages" {
  name           = "${var.environment}-${var.project_name}-chat-messages"
  billing_mode   = "PAY_PER_REQUEST"
  hash_key       = "threadId"
  range_key      = "timestamp"

  attribute {
    name = "threadId"
    type = "S"
  }

  attribute {
    name = "timestamp"
    type = "S"
  }

  attribute {
    name = "userId"
    type = "S"
  }

  attribute {
    name = "channel"
    type = "S"
  }

  attribute {
    name = "messageId"
    type = "S"
  }

  attribute {
    name = "twilioSid"
    type = "S"
  }

  # GSI for querying by user
  global_secondary_index {
    name            = "UserMessagesIndex"
    hash_key        = "userId"
    range_key       = "timestamp"
    projection_type = "ALL"
  }

  # GSI for querying by message UUID (for cost tracking and lookups)
  global_secondary_index {
    name            = "MessageUuidIndex"
    hash_key        = "messageId"
    range_key       = "timestamp"
    projection_type = "ALL"
  }

  # GSI for querying by Twilio SID (for callback cost updates)
  global_secondary_index {
    name            = "TwilioSidIndex"
    hash_key        = "twilioSid"
    projection_type = "ALL"
  }

  # GSI for analytics by channel
  global_secondary_index {
    name            = "ChannelMessagesIndex"
    hash_key        = "channel"
    range_key       = "timestamp"
    projection_type = "ALL"
  }

  ttl {
    attribute_name = "expiresAt"
    enabled        = false  # Set to true if you want messages to auto-expire
  }

  tags = {
    Environment = var.environment
    Purpose     = "Chat message storage"
  }
}

# Chat Sessions Table
resource "aws_dynamodb_table" "chat_sessions" {
  name           = "${var.environment}-${var.project_name}-chat-sessions"
  billing_mode   = "PAY_PER_REQUEST"
  hash_key       = "userId"
  range_key      = "sessionId"

  attribute {
    name = "userId"
    type = "S"
  }

  attribute {
    name = "sessionId"
    type = "S"
  }

  attribute {
    name = "lastMessageAt"
    type = "S"
  }

  # GSI for querying sessions by last message time
  global_secondary_index {
    name            = "SessionsByLastMessageIndex"
    hash_key        = "userId"
    range_key       = "lastMessageAt"
    projection_type = "ALL"
  }

  tags = {
    Environment = var.environment
    Purpose     = "Chat session metadata"
  }
}

# Outputs
output "chat_messages_table_name" {
  description = "Name of the chat messages DynamoDB table"
  value       = aws_dynamodb_table.chat_messages.name
}

output "chat_messages_table_arn" {
  description = "ARN of the chat messages DynamoDB table"
  value       = aws_dynamodb_table.chat_messages.arn
}

output "chat_sessions_table_name" {
  description = "Name of the chat sessions DynamoDB table"
  value       = aws_dynamodb_table.chat_sessions.name
}

output "chat_sessions_table_arn" {
  description = "ARN of the chat sessions DynamoDB table"
  value       = aws_dynamodb_table.chat_sessions.arn
}

