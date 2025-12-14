# Package the SMS Lambda function
# resource "null_resource" "package_users" {
#   provisioner "local-exec" {
#     command = <<EOT
#       cd ${path.module}/../../../backend/lambdas/users && \
#       [ -f users.zip ] && rm users.zip
#       zip -r users.zip .
#     EOT
#   }
#
#   triggers = {
#     force_redeploy = timestamp()
#   }
# }

data "archive_file" "users_zip" {
  type        = "zip"
  source_dir  = "${path.module}/../../../backend/lambdas/users"
  output_path = "${path.module}/../../../backend/lambdas/users/users.zip"
}

# Deploy users Lambda function
resource "aws_lambda_function" "users_function" {
  function_name = "${var.environment}-${var.project_name}-users_function"
  handler       = "users_handler.handler"
  runtime       = "python3.9"
  role          = aws_iam_role.lambda_exec_role.arn
  filename         = data.archive_file.users_zip.output_path
  source_code_hash = data.archive_file.users_zip.output_base64sha256
  layers = [aws_lambda_layer_version.shared_dependencies.arn, "arn:aws:lambda:us-east-1:017000801446:layer:AWSLambdaPowertoolsPythonV3-python39-x86_64:6"]
  # depends_on = [null_resource.package_users]
  timeout       = 30

  environment {
    variables = {
      ENVIRONMENT = var.environment
      PROJECT_NAME = var.project_name
    }

  }

  tags = {
    Environment = var.environment
  }
}

# Lambda Permissions
resource "aws_lambda_permission" "users_permission" {
  statement_id  = "AllowAPIGatewayInvokeSms"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.users_function.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${var.apiGateway_execution_arn}/*/*"
  lifecycle {
    replace_triggered_by = [aws_lambda_function.users_function.id]
  }
}

# Integrate Lambda with API Gateway
resource "aws_apigatewayv2_integration" "lambda_users_integration" {
  api_id           = var.apiGateway_lambda_api_id
  integration_type = "AWS_PROXY"
  integration_uri  = aws_lambda_function.users_function.invoke_arn
}

# Define API Gateway Route
resource "aws_apigatewayv2_route" "lambda_get_users_route" {
  api_id    = var.apiGateway_lambda_api_id
  route_key = "GET /users"
  target    = "integrations/${aws_apigatewayv2_integration.lambda_users_integration.id}"
  authorization_type = "CUSTOM"
  authorizer_id      = var.jwt_auth_id
}

resource "aws_apigatewayv2_route" "lambda_post_users_route" {
  api_id    = var.apiGateway_lambda_api_id
  route_key = "POST /users"
  target    = "integrations/${aws_apigatewayv2_integration.lambda_users_integration.id}"
  authorization_type = "CUSTOM"
  authorizer_id      = var.jwt_auth_id
}

resource "aws_apigatewayv2_route" "lambda_put_users_route" {
  api_id    = var.apiGateway_lambda_api_id
  route_key = "PUT /users"
  target    = "integrations/${aws_apigatewayv2_integration.lambda_users_integration.id}"
  authorization_type = "CUSTOM"
  authorizer_id      = var.jwt_auth_id
}

resource "aws_apigatewayv2_route" "lambda_delete_users_route" {
  api_id    = var.apiGateway_lambda_api_id
  route_key = "DELETE /users"
  target    = "integrations/${aws_apigatewayv2_integration.lambda_users_integration.id}"
  authorization_type = "CUSTOM"
  authorizer_id      = var.jwt_auth_id
}
# resource "aws_apigatewayv2_route" "options_users" {
#   api_id    = var.apiGateway_lambda_api_id
#   route_key = "OPTIONS /users"
#   target    = "integrations/${aws_apigatewayv2_integration.lambda_users_integration.id}"
# }