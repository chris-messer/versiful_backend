# Package the Lambda function
# resource "null_resource" "package_auth" {
#   provisioner "local-exec" {
#     command = <<EOT
#       cd ${path.module}/../../../lambdas/auth && \
#       [ -f auth.zip ] && rm auth.zip
#       zip -r auth.zip .
#     EOT
#   }
#
#   triggers = {
#     force_redeploy = timestamp()
#   }
# }

data "archive_file" "auth_zip" {
  type        = "zip"
  source_dir  = "${path.module}/../../../lambdas/auth"
  output_path = "${path.module}/../../../lambdas/auth/auth.zip"
  excludes = [
    "__pycache__",
    "*.pyc",
    "*.zip",
    ".pytest_cache",
    "*.egg-info"
  ]
}

# Deploy Lambda function
resource "aws_lambda_function" "auth_function" {
  function_name = "${var.environment}-${var.project_name}-auth_function"
  handler       = "auth_handler.handler"
  runtime       = "python3.11"
  role          = aws_iam_role.lambda_exec_role.arn
  filename         = data.archive_file.auth_zip.output_path
  source_code_hash = data.archive_file.auth_zip.output_base64sha256
  # Layers will be added after refactor - currently using self-contained deployment
  # depends_on = [null_resource.package_auth]
  timeout       = 30

  environment {
    variables = {
      ENVIRONMENT = var.environment
      PROJECT_NAME = var.project_name
      CLIENT_ID = var.user_pool_client_id
      USER_POOL_ID = var.user_pool_id
      DOMAIN = var.domain_name
    }

  }

  tags = {
    Environment = var.environment
  }
}

# Lambda Permissions
resource "aws_lambda_permission" "auth_permission" {
  statement_id  = "AllowAPIGatewayInvokeSms"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.auth_function.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${var.apiGateway_execution_arn}/*/*"
  lifecycle {
    replace_triggered_by = [aws_lambda_function.auth_function.id]
  }
}

# Integrate Lambda with API Gateway
resource "aws_apigatewayv2_integration" "lambda_auth_integration" {
  api_id           = var.apiGateway_lambda_api_id
  integration_type = "AWS_PROXY"
  integration_uri  = aws_lambda_function.auth_function.invoke_arn
}

# Define API Gateway Route
resource "aws_apigatewayv2_route" "lambda_auth_post_route" {
  api_id    = var.apiGateway_lambda_api_id
  route_key = "POST /auth/{proxy+}"
  target    = "integrations/${aws_apigatewayv2_integration.lambda_auth_integration.id}"
}
# Define API Gateway Route
resource "aws_apigatewayv2_route" "lambda_auth_put_route" {
  api_id    = var.apiGateway_lambda_api_id
  route_key = "PUT /auth/{proxy+}"
  target    = "integrations/${aws_apigatewayv2_integration.lambda_auth_integration.id}"
}
# Define API Gateway Route
resource "aws_apigatewayv2_route" "lambda_auth_get_route" {
  api_id    = var.apiGateway_lambda_api_id
  route_key = "GET /auth/{proxy+}"
  target    = "integrations/${aws_apigatewayv2_integration.lambda_auth_integration.id}"
}
# Define API Gateway Route
resource "aws_apigatewayv2_route" "lambda_auth_delete_route" {
  api_id    = var.apiGateway_lambda_api_id
  route_key = "DELETE /auth/{proxy+}"
  target    = "integrations/${aws_apigatewayv2_integration.lambda_auth_integration.id}"
}

############### JWT Authorizer ###############
 # Package the Lambda function
# resource "null_resource" "package_authorizer" {
#   provisioner "local-exec" {
#     command = <<EOT
#       cd ${path.module}/../../../lambdas/authorizer && \
#       [ -f auth.zip ] && rm authorizer.zip
#       zip -r authorizer.zip .
#     EOT
#   }
#
#   triggers = {
#     force_redeploy = timestamp()
#   }
# }

data "archive_file" "jwt_authorizer_zip" {
  type        = "zip"
  source_dir  = "${path.module}/../../../lambdas/authorizer"
  output_path = "${path.module}/../../../lambdas/authorizer/authorizer.zip"
  excludes = [
    "__pycache__",
    "*.pyc",
    "*.zip",
    ".pytest_cache",
    "*.egg-info"
  ]
}

# Deploy Lambda function
resource "aws_lambda_function" "jwt_authorizer" {
  function_name = "${var.environment}-${var.project_name}-jwt_authorizer"
  handler       = "jwt_authorizer.handler"
  runtime       = "python3.11"
  role          = aws_iam_role.lambda_exec_role.arn
  filename      = data.archive_file.jwt_authorizer_zip.output_path
  source_code_hash = data.archive_file.jwt_authorizer_zip.output_base64sha256
  # Layers will be added after refactor - currently using self-contained deployment
  # depends_on = [null_resource.package_authorizer]
  timeout       = 30

  environment {
    variables = {
      ENVIRONMENT = var.environment
      PROJECT_NAME = var.project_name
      CLIENT_ID = var.user_pool_client_id
      USER_POOL_ID = var.user_pool_id
      DOMAIN = var.domain_name
      REGION = var.region
    }

  }

  tags = {
    Environment = var.environment
  }
}

# Lambda Permissions
resource "aws_lambda_permission" "authorizer_permission" {
  statement_id  = "AllowAPIGatewayInvokeSms"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.jwt_authorizer.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${var.apiGateway_execution_arn}/*/*"
  lifecycle {
    replace_triggered_by = [aws_lambda_function.jwt_authorizer.id]
  }
}

# Integrate Lambda with API Gateway
resource "aws_apigatewayv2_integration" "lambda_authorizer_integration" {
  api_id           = var.apiGateway_lambda_api_id
  integration_type = "AWS_PROXY"
  integration_uri  = aws_lambda_function.jwt_authorizer.invoke_arn
}