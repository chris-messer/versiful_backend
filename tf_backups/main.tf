






# Package the Web Lambda function
resource "null_resource" "package_web" {
  provisioner "local-exec" {
    command = <<EOT
      cd ${path.module}/../../../lambdas/web && \
      zip -r web.zip .
    EOT
  }

  triggers = {
    force_redeploy = timestamp()
  }
}







# Deploy Web Lambda function
resource "aws_lambda_function" "web_function" {
  function_name = "${var.environment}-web_function"
  handler       = "web_handler.handler"
  runtime       = "python3.9"
  role          = aws_iam_role.lambda_exec_role.arn
  filename      = "${path.module}/../../../lambdas/web/web.zip"
  layers = [aws_lambda_layer_version.shared_dependencies.arn, "arn:aws:lambda:us-east-1:017000801446:layer:AWSLambdaPowertoolsPythonV3-python39-x86_64:6"]
  depends_on = [null_resource.package_web]
  timeout       = 30

  environment {
    variables = {
      ENV_VAR = "web_value"
    }
  }

  tags = {
    Environment = var.environment
  }
}

# API Gateway REST API
resource "aws_api_gateway_rest_api" "api" {
  name        = "${var.environment}-VersifulAPI"
  description = "API Gateway for Lambda functions"
}

# # API Gateway Resources
# resource "aws_api_gateway_resource" "sms_resource" {
#   rest_api_id = aws_api_gateway_rest_api.api.id
#   parent_id   = aws_api_gateway_rest_api.api.root_resource_id
#   path_part   = "sms"
# }

# resource "aws_api_gateway_resource" "web_resource" {
#   rest_api_id = aws_api_gateway_rest_api.api.id
#   parent_id   = aws_api_gateway_rest_api.api.root_resource_id
#   path_part   = "web"
# }

# # SMS Method (POST)
# resource "aws_api_gateway_method" "sms_method" {
#   rest_api_id   = aws_api_gateway_rest_api.api.id
#   resource_id   = aws_api_gateway_resource.sms_resource.id
#   http_method   = "POST"
#   authorization = "NONE"
# }

# # Web Method (POST)
# resource "aws_api_gateway_method" "web_method" {
#   rest_api_id   = aws_api_gateway_rest_api.api.id
#   resource_id   = aws_api_gateway_resource.web_resource.id
#   http_method   = "POST"
#   authorization = "NONE"
# }

# CORS Configuration for Web Resource
resource "aws_api_gateway_method" "web_options" {
  rest_api_id   = aws_api_gateway_rest_api.api.id
  resource_id   = aws_api_gateway_resource.web_resource.id
  http_method   = "OPTIONS"
  authorization = "NONE"
}

resource "aws_api_gateway_integration" "web_options_integration" {
  rest_api_id             = aws_api_gateway_rest_api.api.id
  resource_id             = aws_api_gateway_resource.web_resource.id
  http_method             = aws_api_gateway_method.web_options.http_method
  type                    = "MOCK"

  request_templates = {
    "application/json" = jsonencode({
      statusCode = 200
    })
  }
}

resource "aws_api_gateway_method_response" "web_options_response" {
  rest_api_id   = aws_api_gateway_rest_api.api.id
  resource_id   = aws_api_gateway_resource.web_resource.id
  http_method   = aws_api_gateway_method.web_options.http_method
  status_code   = "200"

  response_parameters = {
    "method.response.header.Access-Control-Allow-Headers" = true,
    "method.response.header.Access-Control-Allow-Methods" = true,
    "method.response.header.Access-Control-Allow-Origin"  = true
  }

  response_models = {
    "application/json" = "Empty"
  }
}

resource "aws_api_gateway_integration_response" "web_options_integration_response" {
  rest_api_id = aws_api_gateway_rest_api.api.id
  resource_id = aws_api_gateway_resource.web_resource.id
  http_method = aws_api_gateway_method.web_options.http_method
  status_code = aws_api_gateway_method_response.web_options_response.status_code

  response_parameters = {
  "method.response.header.Access-Control-Allow-Headers" = "'Content-Type,Authorization'",
  "method.response.header.Access-Control-Allow-Methods" = "'OPTIONS,POST'",
  "method.response.header.Access-Control-Allow-Origin"  = "'*'"
    }

}

# POST Method Response for Web
resource "aws_api_gateway_method_response" "web_post_response" {
  rest_api_id   = aws_api_gateway_rest_api.api.id
  resource_id   = aws_api_gateway_resource.web_resource.id
  http_method   = aws_api_gateway_method.web_method.http_method
  status_code   = "200"

  response_parameters = {
    "method.response.header.Access-Control-Allow-Origin" = true
  }
}

# Integrations
resource "aws_api_gateway_integration" "sms_integration" {
  rest_api_id             = aws_api_gateway_rest_api.api.id
  resource_id             = aws_api_gateway_resource.sms_resource.id
  http_method             = aws_api_gateway_method.sms_method.http_method
  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = aws_lambda_function.sms_function.invoke_arn
}

resource "aws_api_gateway_integration" "web_integration" {
  rest_api_id             = aws_api_gateway_rest_api.api.id
  resource_id             = aws_api_gateway_resource.web_resource.id
  http_method             = aws_api_gateway_method.web_method.http_method
  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = aws_lambda_function.web_function.invoke_arn
}

# Deploy the API Gateway
resource "aws_api_gateway_deployment" "api_deployment" {
  depends_on = [
    aws_api_gateway_integration.sms_integration,
    aws_api_gateway_integration.web_integration,
    aws_api_gateway_integration_response.web_options_integration_response
  ]

  rest_api_id = aws_api_gateway_rest_api.api.id
  description = "Deployment for the ${var.environment} stage"
}

# Define the Stage
resource "aws_api_gateway_stage" "stage" {
  stage_name    = var.environment
  rest_api_id   = aws_api_gateway_rest_api.api.id
  deployment_id = aws_api_gateway_deployment.api_deployment.id

  access_log_settings {
    destination_arn = aws_cloudwatch_log_group.api_gateway_log_group.arn
    format          = "{\"requestId\":\"$context.requestId\",\"ip\":\"$context.identity.sourceIp\",\"userAgent\":\"$context.identity.userAgent\",\"requestTime\":\"$context.requestTime\",\"httpMethod\":\"$context.httpMethod\",\"resourcePath\":\"$context.resourcePath\",\"status\":\"$context.status\",\"protocol\":\"$context.protocol\",\"responseLength\":\"$context.responseLength\"}"
  }

  tags = {
    Environment = var.environment
  }
}



resource "aws_lambda_permission" "web_permission" {
  statement_id  = "AllowAPIGatewayInvokeWeb"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.web_function.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_api_gateway_rest_api.api.execution_arn}/*"
}


# Outputs
output "sms_lambda_url" {
  value       = "${aws_api_gateway_stage.stage.invoke_url}/sms"
  description = "The URL to invoke the SMS Lambda function"
}

output "web_lambda_url" {
  value       = "${aws_api_gateway_stage.stage.invoke_url}/web"
  description = "The URL to invoke the Web Lambda function"
}
