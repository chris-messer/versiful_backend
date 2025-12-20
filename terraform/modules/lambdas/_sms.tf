# Package the SMS Lambda function
# resource "null_resource" "package_sms" {
#   provisioner "local-exec" {
#     command = <<EOT
#       cd ${path.module}/../../../lambdas/sms && \
#       zip -r sms.zip .
#     EOT
#   }
#
#   triggers = {
#     force_redeploy = timestamp()
#   }
# }

data "archive_file" "sms_zip" {
  type        = "zip"
  source_dir  = "${path.module}/../../../lambdas/sms"
  output_path = "${path.module}/../../../lambdas/sms/sms.zip"
  excludes = [
    "__pycache__",
    "*.pyc",
    "*.zip",
    ".pytest_cache",
    "*.egg-info"
  ]
}

# Deploy SMS Lambda function
resource "aws_lambda_function" "sms_function" {
  function_name = "${var.environment}-sms_function"
  handler       = "sms_handler.handler"
  runtime       = "python3.9"
  role          = aws_iam_role.lambda_exec_role.arn
  filename      = data.archive_file.sms_zip.output_path
  source_code_hash = data.archive_file.sms_zip.output_base64sha256
  layers = [aws_lambda_layer_version.shared_dependencies.arn, "arn:aws:lambda:us-east-1:017000801446:layer:AWSLambdaPowertoolsPythonV3-python39-x86_64:6"]
  # depends_on = [null_resource.package_sms]
  timeout       = 30

  environment {
    variables = {
      ENVIRONMENT       = var.environment
      PROJECT_NAME      = var.project_name
      SMS_USAGE_TABLE   = "${var.environment}-${var.project_name}-sms-usage"
      USERS_TABLE       = "${var.environment}-${var.project_name}-users"
      FREE_MONTHLY_LIMIT= "5"
      NUDGE_LIMIT       = "3"
    }

  }

  tags = {
    Environment = var.environment
  }
}

# Lambda Permissions
resource "aws_lambda_permission" "sms_permission" {
  statement_id  = "AllowAPIGatewayInvokeSms"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.sms_function.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${var.apiGateway_execution_arn}/*/*"
  lifecycle {
    replace_triggered_by = [aws_lambda_function.sms_function.id]
  }
}

# Integrate Lambda with API Gateway
resource "aws_apigatewayv2_integration" "lambda_integration" {
  api_id           = var.apiGateway_lambda_api_id
  integration_type = "AWS_PROXY"
  integration_uri  = aws_lambda_function.sms_function.invoke_arn
}

# Define API Gateway Route
resource "aws_apigatewayv2_route" "lambda_route" {
  api_id    = var.apiGateway_lambda_api_id
  route_key = "ANY /sms"
  target    = "integrations/${aws_apigatewayv2_integration.lambda_integration.id}"
}
