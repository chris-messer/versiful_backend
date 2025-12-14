# Package the Lambda function
resource "null_resource" "package_cors" {
  provisioner "local-exec" {
    command = <<EOT
      cd ${path.module}/../../../backend/lambdas/cors && \
      [ -f cors.zip ] && rm cors.zip
      zip -r cors.zip .
    EOT
  }

#   triggers = {
#     force_redeploy = timestamp()
#   }
}

data "archive_file" "cors_zip" {
  type        = "zip"
  source_dir  = "${path.module}/../../../backend/lambdas/cors"
  output_path = "${path.module}/../../../backend/lambdas/cors/cors.zip"
}

# Deploy Lambda function
resource "aws_lambda_function" "cors_function" {
  function_name = "${var.environment}-${var.project_name}-cors_function"
  handler       = "cors_handler.handler"
  runtime       = "python3.9"
  role          = aws_iam_role.lambda_exec_role.arn
  filename         = data.archive_file.cors_zip.output_path
  source_code_hash = data.archive_file.cors_zip.output_base64sha256
  layers = [aws_lambda_layer_version.shared_dependencies.arn, "arn:aws:lambda:us-east-1:017000801446:layer:AWSLambdaPowertoolsPythonV3-python39-x86_64:6"]
  # depends_on = [null_resource.package_cors]
  timeout       = 30

  environment {
    variables = {
      ALLOWED_CORS_ORIGINS = join(",", var.allowed_cors_origins)
    }
  }

  tags = {
    Environment = var.environment
  }
}

# Lambda Permissions
resource "aws_lambda_permission" "cors_permission" {
  statement_id  = "AllowAPIGatewayInvokeSms"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.cors_function.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${var.apiGateway_execution_arn}/*/*"
  lifecycle {
    replace_triggered_by = [aws_lambda_function.cors_function.id]
  }
}

# Integrate Lambda with API Gateway
resource "aws_apigatewayv2_integration" "lambda_options_integration" {
  api_id           = var.apiGateway_lambda_api_id
  integration_type = "AWS_PROXY"
  integration_uri  = aws_lambda_function.cors_function.invoke_arn
}

resource "aws_apigatewayv2_route" "options_route" {
  api_id    = var.apiGateway_lambda_api_id
  route_key = "OPTIONS /{proxy+}"
  target    = "integrations/${aws_apigatewayv2_integration.lambda_options_integration.id}"
}