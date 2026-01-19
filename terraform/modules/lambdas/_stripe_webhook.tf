# Package the Stripe Webhook Lambda function
data "archive_file" "stripe_webhook_zip" {
  type        = "zip"
  source_dir  = "${path.module}/../../../lambdas/stripe_webhook"
  output_path = "${path.module}/../../../lambdas/stripe_webhook/webhook.zip"
  excludes = [
    "__pycache__",
    "*.pyc",
    "*.zip",
    ".pytest_cache",
    "*.egg-info"
  ]
}

# Deploy Stripe webhook Lambda function
resource "aws_lambda_function" "stripe_webhook_function" {
  function_name    = "${var.environment}-${var.project_name}-stripe-webhook"
  handler          = "webhook_handler.handler"
  runtime          = "python3.11"
  role             = aws_iam_role.lambda_exec_role.arn
  filename         = data.archive_file.stripe_webhook_zip.output_path
  source_code_hash = data.archive_file.stripe_webhook_zip.output_base64sha256
  timeout          = 30

  # Use Lambda layer for shared dependencies (stripe, secrets_helper)
  layers = [aws_lambda_layer_version.shared_dependencies.arn]

  environment {
    variables = {
      ENVIRONMENT    = var.environment
      PROJECT_NAME   = var.project_name
      SECRET_ARN     = var.secret_arn
      VERSIFUL_PHONE = var.versiful_phone
    }
  }

  tags = {
    Environment = var.environment
    Service     = "stripe-webhook"
  }
}

# Lambda Permission for API Gateway
resource "aws_lambda_permission" "stripe_webhook_permission" {
  statement_id  = "AllowAPIGatewayInvokeStripeWebhook"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.stripe_webhook_function.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${var.apiGateway_execution_arn}/*/*"
  
  lifecycle {
    replace_triggered_by = [aws_lambda_function.stripe_webhook_function.id]
  }
}

# API Gateway Integration
resource "aws_apigatewayv2_integration" "stripe_webhook_integration" {
  api_id           = var.apiGateway_lambda_api_id
  integration_type = "AWS_PROXY"
  integration_uri  = aws_lambda_function.stripe_webhook_function.invoke_arn
}

# Route: POST /stripe/webhook
# IMPORTANT: No JWT auth - Stripe cannot send JWT tokens
# Security is handled via webhook signature verification in the Lambda function
resource "aws_apigatewayv2_route" "stripe_webhook" {
  api_id    = var.apiGateway_lambda_api_id
  route_key = "POST /stripe/webhook"
  target    = "integrations/${aws_apigatewayv2_integration.stripe_webhook_integration.id}"
  # No authorization_type - signature verification happens in Lambda
}

