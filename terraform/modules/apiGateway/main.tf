locals {
  env_prefix  = var.environment
  domain      = "${local.env_prefix}.${var.domain_name}"         # prod.versiful.io, dev.versiful.io, etc.
  api_domain  = "api.${local.env_prefix}.${var.domain_name}"     # api.prod.versiful.io, etc.
  auth_domain = "auth.${local.env_prefix}.${var.domain_name}"    # auth.prod.versiful.io, etc.
}


# API Gateway v2 (HTTP API)
resource "aws_apigatewayv2_api" "lambda_api" {
  name          = "${var.environment}-${var.project_name}-gateway"
  protocol_type = "HTTP"

  cors_configuration {  # Correct indentation
    allow_origins = var.allowed_cors_origins
    allow_methods = ["OPTIONS", "GET", "POST", "PUT", "DELETE"]
    allow_headers = ["Content-Type", "Authorization"]
    allow_credentials = true
  }
}

# CloudWatch Log Group for API Gateway (environment-specific)
resource "aws_cloudwatch_log_group" "api_gateway_log_group" {
  name              = "/aws/api-gateway/${var.environment}-${var.project_name}"
  retention_in_days = 7
  
  tags = {
    Environment = var.environment
  }
}

# Deploy API Gateway Stage (Auto Deploy Enabled)
resource "aws_apigatewayv2_stage" "lambda_stage" {
  api_id      = aws_apigatewayv2_api.lambda_api.id
  depends_on  = [aws_apigatewayv2_api.lambda_api, aws_cloudwatch_log_group.api_gateway_log_group]
  name        = var.environment
  auto_deploy = true

  access_log_settings {
    destination_arn = aws_cloudwatch_log_group.api_gateway_log_group.arn
    format = jsonencode({
      requestId            = "$context.requestId"
      ip                   = "$context.identity.sourceIp"
      requestTime          = "$context.requestTime"
      httpMethod           = "$context.httpMethod"
      routeKey             = "$context.routeKey"
      status               = "$context.status"
      protocol             = "$context.protocol"
      responseLength       = "$context.responseLength"
      message              = "$context.integration.request.body"
      integrationStatus    = "$context.integration.status"
      integrationError     = "$context.integration.error"
      integrationLatency   = "$context.integration.latency"
      integrationRequestId = "$context.integration.requestId"
      integrationEndpoint  = "$context.integration.integrationId"
    })
  }
}

# Wait for ACM Certificate Validation Before Proceeding
resource "null_resource" "wait_for_acm_validation" {
  depends_on = [aws_apigatewayv2_api.lambda_api]
  provisioner "local-exec" {
    command = <<EOT
      CERT_ARN="${var.acm_api_certificate_arn}"
      while true; do
        STATUS=$(aws acm describe-certificate --certificate-arn $CERT_ARN --region ${var.region} --query "Certificate.Status" --output text)
        echo "ACM Certificate Status: $STATUS"
        if [ "$STATUS" == "ISSUED" ]; then
          echo "Certificate validated!"
          break
        fi
        echo "Waiting for ACM validation..."
        sleep 10
      done
    EOT
  }

  triggers = {
    cert_arn = var.acm_api_certificate_arn
  }
}

# Custom Domain for API Gateway
resource "aws_apigatewayv2_domain_name" "api_domain" {
  domain_name = local.api_domain
  depends_on  = [null_resource.wait_for_acm_validation]

  domain_name_configuration {
    certificate_arn = var.acm_api_certificate_arn
    endpoint_type   = "REGIONAL"
    security_policy = "TLS_1_2"
  }
}

# API Mapping for Each Environment
resource "aws_apigatewayv2_api_mapping" "api_mapping" {
  api_id      = aws_apigatewayv2_api.lambda_api.id
  domain_name = aws_apigatewayv2_domain_name.api_domain.id
  stage       = aws_apigatewayv2_stage.lambda_stage.id
}

# JWT Authorizer for secure auth
resource "aws_apigatewayv2_authorizer" "jwt_auth" {
  api_id          = aws_apigatewayv2_api.lambda_api.id
  name            = "JWTAuthorizer"
  authorizer_type = "REQUEST"
  authorizer_uri  = var.authorizer_uri
  identity_sources = ["$request.header.cookie"]
  authorizer_payload_format_version = "2.0"
  enable_simple_responses           = true
}