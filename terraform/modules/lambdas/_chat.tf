# Chat Lambda Function - Core chat handler

# Package the Chat Lambda function
data "archive_file" "chat_zip" {
  type        = "zip"
  source_dir  = "${path.module}/../../../lambdas/chat"
  output_path = "${path.module}/../../../lambdas/chat/chat.zip"
  excludes = [
    "__pycache__",
    "*.pyc",
    "*.zip",
    ".pytest_cache",
    "*.egg-info"
  ]
}

# Deploy Chat Lambda function
resource "aws_lambda_function" "chat_function" {
  function_name    = "${var.environment}-${var.project_name}-chat"
  handler          = "chat_handler.handler"
  runtime          = "python3.11"
  role             = aws_iam_role.lambda_exec_role.arn
  filename         = data.archive_file.chat_zip.output_path
  source_code_hash = data.archive_file.chat_zip.output_base64sha256
  
  # The langchain layer now vendors the shared Python modules (secrets_helper, the
  # neon/memory modules, the promoted agent-tool modules) alongside its heavy deps
  # (openai/langgraph/psycopg/pydantic/posthog), so chat needs only core + langchain.
  # We intentionally do NOT mount shared_dependencies here: it re-bundles twilio/stripe/
  # cryptography + a duplicate openai/pydantic stack that chat doesn't need, and stacking
  # it on top of langchain pushed the unzipped layers past the 250 MB Lambda limit.
  layers = [
    aws_lambda_layer_version.core_layer.arn,
    aws_lambda_layer_version.langchain_layer.arn
  ]
  
  timeout      = 60  # Longer timeout for LLM calls
  memory_size  = 512  # More memory for LangChain

  environment {
    variables = {
      ENVIRONMENT           = var.environment
      PROJECT_NAME          = var.project_name
      SECRET_ARN            = var.secret_arn
      CHAT_MESSAGES_TABLE   = aws_dynamodb_table.chat_messages.name
      CHAT_SESSIONS_TABLE   = aws_dynamodb_table.chat_sessions.name
      USERS_TABLE           = "${var.environment}-${var.project_name}-users"
      VERSE_HISTORY_TABLE   = aws_dynamodb_table.verse_history.name
      # Companion agent tools (save_prayer / account / reading-plan / get_account_status)
      # read these at runtime. IAM already covers them: companion_dynamodb_access grants
      # prayers + user_reading_plans, and dynamodb_access grants sms_usage.
      PRAYERS_TABLE            = aws_dynamodb_table.prayers.name
      USER_READING_PLANS_TABLE = aws_dynamodb_table.user_reading_plans.name
      SMS_USAGE_TABLE          = "${var.environment}-${var.project_name}-sms-usage"
      # Self-invoke target for async SMS memory extraction (spec §5.2). Literal name
      # (not a self-reference) avoids a resource dependency cycle.
      CHAT_FUNCTION_NAME    = "${var.environment}-${var.project_name}-chat"
      POSTHOG_API_KEY       = var.posthog_apikey
    }
  }

  tags = {
    Environment = var.environment
    Purpose     = "Chat message processing"
  }
}

# Web Chat Handler Lambda - REST API for web interface
data "archive_file" "web_chat_zip" {
  type        = "zip"
  source_dir  = "${path.module}/../../../lambdas/chat"
  output_path = "${path.module}/../../../lambdas/chat/web_chat.zip"
  excludes = [
    "__pycache__",
    "*.pyc",
    "*.zip",
    ".pytest_cache",
    "*.egg-info"
  ]
}

resource "aws_lambda_function" "web_chat_function" {
  function_name    = "${var.environment}-${var.project_name}-web-chat"
  handler          = "web_handler.handler"
  runtime          = "python3.11"
  role             = aws_iam_role.lambda_exec_role.arn
  filename         = data.archive_file.web_chat_zip.output_path
  source_code_hash = data.archive_file.web_chat_zip.output_base64sha256
  
  # Same layering rationale as chat_function: the langchain layer carries both the
  # heavy deps and the shared modules (web_handler -> chat_handler -> agent_service can
  # import them), so core + langchain is sufficient and stays under the 250 MB limit.
  layers = [
    aws_lambda_layer_version.core_layer.arn,
    aws_lambda_layer_version.langchain_layer.arn
  ]
  
  timeout      = 30
  memory_size  = 256

  environment {
    variables = {
      ENVIRONMENT           = var.environment
      PROJECT_NAME          = var.project_name
      SECRET_ARN            = var.secret_arn
      CHAT_MESSAGES_TABLE   = aws_dynamodb_table.chat_messages.name
      CHAT_SESSIONS_TABLE   = aws_dynamodb_table.chat_sessions.name
      USERS_TABLE           = "${var.environment}-${var.project_name}-users"
      VERSE_HISTORY_TABLE   = aws_dynamodb_table.verse_history.name
      CHAT_FUNCTION_NAME    = aws_lambda_function.chat_function.function_name
      CORS_ORIGIN           = var.allowed_cors_origins[0]
      POSTHOG_API_KEY       = var.posthog_apikey
      # web_handler -> chat_handler -> agent_service can run the agent in-process, so it
      # needs the same companion-tool table env vars as chat_function.
      PRAYERS_TABLE            = aws_dynamodb_table.prayers.name
      USER_READING_PLANS_TABLE = aws_dynamodb_table.user_reading_plans.name
      SMS_USAGE_TABLE          = "${var.environment}-${var.project_name}-sms-usage"
    }
  }

  tags = {
    Environment = var.environment
    Purpose     = "Web chat API"
  }
}

# Lambda Permissions for API Gateway
resource "aws_lambda_permission" "web_chat_permission" {
  statement_id  = "AllowAPIGatewayInvokeWebChat"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.web_chat_function.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${var.apiGateway_execution_arn}/*/*"
  
  lifecycle {
    replace_triggered_by = [aws_lambda_function.web_chat_function.id]
  }
}

# Allow web chat lambda to invoke chat lambda
resource "aws_lambda_permission" "web_chat_invoke_chat" {
  statement_id  = "AllowWebChatInvokeChat"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.chat_function.function_name
  principal     = "lambda.amazonaws.com"
  source_arn    = aws_lambda_function.web_chat_function.arn
}

# Allow the chat lambda to invoke ITSELF asynchronously for memory extraction
# (spec §5.2 "async for SMS"). chat_handler does an InvocationType='Event'
# self-invoke; without this it falls back to running extraction inline.
#
# NOTE: an account-wide invoke policy (lambda_invoke_policy, Resource="*") is already
# attached to lambda_exec_role, so this scoped grant is additive/explicit (least-
# privilege intent for the self-invoke path) and documents the dependency.
resource "aws_iam_policy" "chat_self_invoke" {
  name        = "${var.environment}-${var.project_name}-chat-self-invoke"
  description = "Allow the chat lambda to invoke itself (async SMS memory extraction)"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = ["lambda:InvokeFunction"]
        Resource = [
          aws_lambda_function.chat_function.arn,
          "${aws_lambda_function.chat_function.arn}:*"
        ]
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "attach_chat_self_invoke" {
  role       = aws_iam_role.lambda_exec_role.name
  policy_arn = aws_iam_policy.chat_self_invoke.arn
}

# API Gateway Integration - POST /chat/message
resource "aws_apigatewayv2_integration" "chat_message_integration" {
  api_id           = var.apiGateway_lambda_api_id
  integration_type = "AWS_PROXY"
  integration_uri  = aws_lambda_function.web_chat_function.invoke_arn
}

resource "aws_apigatewayv2_route" "chat_message_route" {
  api_id             = var.apiGateway_lambda_api_id
  route_key          = "POST /chat/message"
  target             = "integrations/${aws_apigatewayv2_integration.chat_message_integration.id}"
  authorization_type = "CUSTOM"
  authorizer_id      = var.jwt_auth_id
}

# API Gateway Integration - GET /chat/sessions
resource "aws_apigatewayv2_integration" "chat_sessions_list_integration" {
  api_id           = var.apiGateway_lambda_api_id
  integration_type = "AWS_PROXY"
  integration_uri  = aws_lambda_function.web_chat_function.invoke_arn
}

resource "aws_apigatewayv2_route" "chat_sessions_list_route" {
  api_id             = var.apiGateway_lambda_api_id
  route_key          = "GET /chat/sessions"
  target             = "integrations/${aws_apigatewayv2_integration.chat_sessions_list_integration.id}"
  authorization_type = "CUSTOM"
  authorizer_id      = var.jwt_auth_id
}

# API Gateway Integration - POST /chat/sessions
resource "aws_apigatewayv2_integration" "chat_sessions_create_integration" {
  api_id           = var.apiGateway_lambda_api_id
  integration_type = "AWS_PROXY"
  integration_uri  = aws_lambda_function.web_chat_function.invoke_arn
}

resource "aws_apigatewayv2_route" "chat_sessions_create_route" {
  api_id             = var.apiGateway_lambda_api_id
  route_key          = "POST /chat/sessions"
  target             = "integrations/${aws_apigatewayv2_integration.chat_sessions_create_integration.id}"
  authorization_type = "CUSTOM"
  authorizer_id      = var.jwt_auth_id
}

# API Gateway Integration - GET /chat/sessions/{sessionId}
resource "aws_apigatewayv2_integration" "chat_session_get_integration" {
  api_id           = var.apiGateway_lambda_api_id
  integration_type = "AWS_PROXY"
  integration_uri  = aws_lambda_function.web_chat_function.invoke_arn
}

resource "aws_apigatewayv2_route" "chat_session_get_route" {
  api_id             = var.apiGateway_lambda_api_id
  route_key          = "GET /chat/sessions/{sessionId}"
  target             = "integrations/${aws_apigatewayv2_integration.chat_session_get_integration.id}"
  authorization_type = "CUSTOM"
  authorizer_id      = var.jwt_auth_id
}

# API Gateway Integration - DELETE /chat/sessions/{sessionId}
resource "aws_apigatewayv2_integration" "chat_session_delete_integration" {
  api_id           = var.apiGateway_lambda_api_id
  integration_type = "AWS_PROXY"
  integration_uri  = aws_lambda_function.web_chat_function.invoke_arn
}

resource "aws_apigatewayv2_route" "chat_session_delete_route" {
  api_id             = var.apiGateway_lambda_api_id
  route_key          = "DELETE /chat/sessions/{sessionId}"
  target             = "integrations/${aws_apigatewayv2_integration.chat_session_delete_integration.id}"
  authorization_type = "CUSTOM"
  authorizer_id      = var.jwt_auth_id
}

# API Gateway Integration - PUT /chat/sessions/{sessionId}/title
resource "aws_apigatewayv2_integration" "chat_session_title_update_integration" {
  api_id           = var.apiGateway_lambda_api_id
  integration_type = "AWS_PROXY"
  integration_uri  = aws_lambda_function.web_chat_function.invoke_arn
}

resource "aws_apigatewayv2_route" "chat_session_title_update_route" {
  api_id             = var.apiGateway_lambda_api_id
  route_key          = "PUT /chat/sessions/{sessionId}/title"
  target             = "integrations/${aws_apigatewayv2_integration.chat_session_title_update_integration.id}"
  authorization_type = "CUSTOM"
  authorizer_id      = var.jwt_auth_id
}

# CORS routes for chat endpoints
resource "aws_apigatewayv2_route" "chat_message_options" {
  api_id    = var.apiGateway_lambda_api_id
  route_key = "OPTIONS /chat/message"
  target    = "integrations/${aws_apigatewayv2_integration.chat_message_integration.id}"
}

resource "aws_apigatewayv2_route" "chat_sessions_options" {
  api_id    = var.apiGateway_lambda_api_id
  route_key = "OPTIONS /chat/sessions"
  target    = "integrations/${aws_apigatewayv2_integration.chat_sessions_list_integration.id}"
}

resource "aws_apigatewayv2_route" "chat_session_detail_options" {
  api_id    = var.apiGateway_lambda_api_id
  route_key = "OPTIONS /chat/sessions/{sessionId}"
  target    = "integrations/${aws_apigatewayv2_integration.chat_session_get_integration.id}"
}

resource "aws_apigatewayv2_route" "chat_session_title_options" {
  api_id    = var.apiGateway_lambda_api_id
  route_key = "OPTIONS /chat/sessions/{sessionId}/title"
  target    = "integrations/${aws_apigatewayv2_integration.chat_session_title_update_integration.id}"
}

