# Package the Subscription Lambda function
data "archive_file" "subscription_zip" {
  type        = "zip"
  source_dir  = "${path.module}/../../../lambdas/subscription"
  output_path = "${path.module}/../../../lambdas/subscription/subscription.zip"
  excludes = [
    "__pycache__",
    "*.pyc",
    "*.zip",
    ".pytest_cache",
    "*.egg-info"
  ]
}

# Deploy subscription Lambda function
resource "aws_lambda_function" "subscription_function" {
  function_name    = "${var.environment}-${var.project_name}-subscription"
  handler          = "subscription_handler.handler"
  runtime          = "python3.11"
  role             = aws_iam_role.lambda_exec_role.arn
  filename         = data.archive_file.subscription_zip.output_path
  source_code_hash = data.archive_file.subscription_zip.output_base64sha256
  timeout          = 30

  # Use Lambda layer for shared dependencies (stripe, secrets_helper)
  layers = [aws_lambda_layer_version.shared_dependencies.arn]

  environment {
    variables = {
      ENVIRONMENT      = var.environment
      PROJECT_NAME     = var.project_name
      SECRET_ARN       = var.secret_arn
      FRONTEND_DOMAIN  = var.frontend_domain
    }
  }

  tags = {
    Environment = var.environment
    Service     = "stripe-subscription"
  }
}

# Lambda Permission for API Gateway
resource "aws_lambda_permission" "subscription_permission" {
  statement_id  = "AllowAPIGatewayInvokeSubscription"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.subscription_function.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${var.apiGateway_execution_arn}/*/*"
  
  lifecycle {
    replace_triggered_by = [aws_lambda_function.subscription_function.id]
  }
}

# API Gateway Integration
resource "aws_apigatewayv2_integration" "subscription_integration" {
  api_id           = var.apiGateway_lambda_api_id
  integration_type = "AWS_PROXY"
  integration_uri  = aws_lambda_function.subscription_function.invoke_arn
}

# Route: POST /subscription/checkout (requires JWT auth)
resource "aws_apigatewayv2_route" "subscription_checkout" {
  api_id             = var.apiGateway_lambda_api_id
  route_key          = "POST /subscription/checkout"
  target             = "integrations/${aws_apigatewayv2_integration.subscription_integration.id}"
  authorization_type = "CUSTOM"
  authorizer_id      = var.jwt_auth_id
}

# Route: POST /subscription/portal (requires JWT auth)
resource "aws_apigatewayv2_route" "subscription_portal" {
  api_id             = var.apiGateway_lambda_api_id
  route_key          = "POST /subscription/portal"
  target             = "integrations/${aws_apigatewayv2_integration.subscription_integration.id}"
  authorization_type = "CUSTOM"
  authorizer_id      = var.jwt_auth_id
}

# Route: GET /subscription/prices (public - no auth required)
resource "aws_apigatewayv2_route" "subscription_prices" {
  api_id    = var.apiGateway_lambda_api_id
  route_key = "GET /subscription/prices"
  target    = "integrations/${aws_apigatewayv2_integration.subscription_integration.id}"
  # No authorization_type - public endpoint
}

