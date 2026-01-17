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
        Action   = [
          "dynamodb:GetItem", 
          "dynamodb:PutItem", 
          "dynamodb:UpdateItem",
          "dynamodb:Query",
          "dynamodb:Scan"
        ]
        Resource = [
          var.users_dynamodb_arn, 
          var.sms_usage_dynamodb_arn,
          "${var.users_dynamodb_arn}/*",
          "${var.sms_usage_dynamodb_arn}/*"
        ]
      }
    ]
  })
}

# Grant access to chat DynamoDB tables
resource "aws_iam_policy" "chat_dynamodb_access" {
  name        = "${var.environment}-${var.project_name}-chat-dynamodb-access"
  description = "Allow Lambda to access Chat DynamoDB tables"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = [
          "dynamodb:GetItem", 
          "dynamodb:PutItem", 
          "dynamodb:UpdateItem",
          "dynamodb:Query",
          "dynamodb:Scan"
        ]
        Resource = [
          aws_dynamodb_table.chat_messages.arn,
          "${aws_dynamodb_table.chat_messages.arn}/*",
          aws_dynamodb_table.chat_sessions.arn,
          "${aws_dynamodb_table.chat_sessions.arn}/*"
        ]
      }
    ]
  })
}

# Grant Lambda invoke permissions (for SMS/Web to invoke Chat)
resource "aws_iam_policy" "lambda_invoke_policy" {
  name        = "${var.environment}-${var.project_name}-lambda-invoke"
  description = "Allow Lambda to invoke other Lambdas"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["lambda:InvokeFunction"]
        Resource = "*"
      }
    ]
  })
}

# Grant Lambdas access to secret manager
resource "aws_iam_policy" "secrets_manager_policy" {
  name        = "${var.environment}-${var.project_name}-LambdaSecretsManagerPolicy"
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

# Grant Lambdas access to Cognito user pool admin operations
resource "aws_iam_policy" "cognito_admin_policy" {
  name        = "${var.environment}-${var.project_name}-LambdaCognitoAdminPolicy"
  description = "Allows Lambda to perform Cognito admin operations for user signup"
  tags = {
    Environment = var.environment
  }
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = [
          "cognito-idp:AdminConfirmSignUp",
          "cognito-idp:AdminGetUser",
          "cognito-idp:AdminUpdateUserAttributes"
        ]
        Effect   = "Allow"
        Resource = "arn:aws:cognito-idp:${var.region}:*:userpool/${var.user_pool_id}"
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

# Attach dynamodb policy to role
resource "aws_iam_role_policy_attachment" "attach_dynamodb_policy" {
  role       = aws_iam_role.lambda_exec_role.name
  policy_arn = aws_iam_policy.dynamodb_access.arn
}

# Attach chat dynamodb policy to role
resource "aws_iam_role_policy_attachment" "attach_chat_dynamodb_policy" {
  role       = aws_iam_role.lambda_exec_role.name
  policy_arn = aws_iam_policy.chat_dynamodb_access.arn
}

# Attach lambda invoke policy to role
resource "aws_iam_role_policy_attachment" "attach_lambda_invoke_policy" {
  role       = aws_iam_role.lambda_exec_role.name
  policy_arn = aws_iam_policy.lambda_invoke_policy.arn
}

# Attach cognito admin policy to role
resource "aws_iam_role_policy_attachment" "attach_cognito_admin_policy" {
  role       = aws_iam_role.lambda_exec_role.name
  policy_arn = aws_iam_policy.cognito_admin_policy.arn
}

# Note: aws_api_gateway_account and related IAM role removed
# API Gateway v2 (HTTP API) handles CloudWatch logging differently than REST API
# Logging is configured per-stage in the apiGateway module via access_log_settings
# This prevents singleton resource conflicts across environments
# CloudWatch log group is also managed in the apiGateway module

# Package the layer
resource "null_resource" "package_layer" {
  provisioner "local-exec" {
    command = <<EOT
      cd ${path.module}/../../../lambdas/layer && \
      rm -rf python && \
      mkdir python && \
      pip install -r requirements.txt -t python && \
      cp ../shared/*.py python/ && \
      zip -r layer.zip python
    EOT
  }

  triggers = {
    requirements   = filemd5("${path.module}/../../../lambdas/layer/requirements.txt")
    shared_secrets = filemd5("${path.module}/../../../lambdas/shared/secrets_helper.py")
    shared_sms     = filemd5("${path.module}/../../../lambdas/shared/sms_notifications.py")
  }
}
resource "aws_lambda_layer_version" "shared_dependencies" {
  filename         = "${path.module}/../../../lambdas/layer/layer.zip"
  layer_name       = "shared_dependencies"
  compatible_runtimes = ["python3.11", "python3.9"]
  source_code_hash = filebase64sha256("${path.module}/../../../lambdas/layer/layer.zip")
  depends_on = [null_resource.package_layer]
}