# IAM Role for Lambda execution
resource "aws_iam_role" "lambda_exec_role" {
  name = "${var.environment}-lambda_exec_role"
  tags = {
    Environment = var.environment
  }
  assume_role_policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Effect = "Allow",
        Principal = {
          Service = "lambda.amazonaws.com"
        },
        Action = "sts:AssumeRole"
      }
    ]
  })
}

# Grant access to dynamodb
resource "aws_iam_policy" "dynamodb_access" {
  name        = "${var.environment}-${var.project_name}-dynamodb_access"
  description = "Allow Lambda to access DynamoDB"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["dynamodb:GetItem", "dynamodb:PutItem"]
        Resource = var.users_dynamodb_arn
      }
    ]
  })
}

#TODO add in project name to the role name
# Grant Lambdas access to secret manager
resource "aws_iam_policy" "secrets_manager_policy" {
  name        = "${var.environment}-LambdaSecretsManagerPolicy"
  description = "Allows Lambda to access secrets in AWS Secrets Manager"
  tags = {
    Environment = var.environment
  }
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = [
          "secretsmanager:GetSecretValue"
        ]
        Effect   = "Allow"
        Resource = var.secret_arn
      }
    ]
  })
}

# Attach execute policy to role
resource "aws_iam_role_policy_attachment" "lambda_policy" {
  role       = aws_iam_role.lambda_exec_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# Attach secrets policy to role
resource "aws_iam_role_policy_attachment" "attach_policy" {
  role       = aws_iam_role.lambda_exec_role.name
  policy_arn = aws_iam_policy.secrets_manager_policy.arn
}

# Attach secrets policy to role
resource "aws_iam_role_policy_attachment" "attach_dynamodb_policy" {
  role       = aws_iam_role.lambda_exec_role.name
  policy_arn = aws_iam_policy.dynamodb_access.arn
}

# IAM Role for API Gateway CloudWatch Logs
#TODO add in project name to the role name
resource "aws_iam_role" "api_gateway_cloudwatch_role" {
  name = "${var.environment}-APIGatewayCloudWatchLogsRole"
  tags = {
    Environment = var.environment
  }
  assume_role_policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Effect = "Allow",
        Principal = {
          Service = "apigateway.amazonaws.com"
        },
        Action = "sts:AssumeRole"
      }
    ]
  })
}

#TODO add in project name to the role name
resource "aws_iam_policy_attachment" "api_gateway_logs_policy" {
  name       = "${var.environment}-APIGatewayLogsPolicyAttachment"
  roles      = [aws_iam_role.api_gateway_cloudwatch_role.name]
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonAPIGatewayPushToCloudWatchLogs"
}

# Associate CloudWatch Logs Role with API Gateway Account
resource "aws_api_gateway_account" "account_settings" {
  cloudwatch_role_arn = aws_iam_role.api_gateway_cloudwatch_role.arn
}

# CloudWatch Log Group for API Gateway
#TODO add in project name to the role name
resource "aws_cloudwatch_log_group" "api_gateway_log_group" {
  name              = "/aws/api-gateway/${var.environment}-stage"
  retention_in_days = 7
}

# Package the layer
resource "null_resource" "package_layer" {
  provisioner "local-exec" {
    command = <<EOT
      cd ${path.module}/../../../lambdas/layer && \
      rm -rf python && \
      mkdir python && \
      pip install -r requirements.txt -t python
      pip3 install --upgrade --platform manylinux_2_17_aarch64 --only-binary=:all: pydantic-core==2.14.1 -t python && \
      zip -r layer.zip python
    EOT
  }

#   triggers = {
#     force_redeploy = timestamp()
#   }
}
resource "aws_lambda_layer_version" "shared_dependencies" {
  filename         = "${path.module}/../../../lambdas/layer/layer.zip"
  layer_name       = "shared_dependencies"
  compatible_runtimes = ["python3.9"]
  depends_on = [null_resource.package_layer]
}