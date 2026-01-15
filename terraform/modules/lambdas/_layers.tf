# Optimized Lambda Layers - Phase 2
# Created: Dec 21, 2025
# Purpose: Smaller, function-specific layers to stay under AWS 250MB limit

# ============================================
# Core Layer - requests only (~2 MB compressed)
# Used by: SMS, Auth, Authorizer functions
# ============================================

resource "null_resource" "package_core_layer" {
  provisioner "local-exec" {
    command = <<EOT
      cd ${path.module}/../../../lambdas/layers/core && \
      rm -rf python && \
      mkdir python && \
      pip install -r requirements.txt -t python --platform manylinux2014_x86_64 --only-binary=:all: --python-version 3.11 && \
      zip -r layer.zip python
    EOT
  }

  triggers = {
    requirements = filemd5("${path.module}/../../../lambdas/layers/core/requirements.txt")
  }
}

resource "aws_lambda_layer_version" "core_layer" {
  filename            = "${path.module}/../../../lambdas/layers/core/layer.zip"
  layer_name          = "${var.environment}-core-dependencies"
  compatible_runtimes = ["python3.11"]
  description         = "Core dependencies: requests"
  source_code_hash    = filebase64sha256("${path.module}/../../../lambdas/layers/core/layer.zip")
  
  depends_on = [null_resource.package_core_layer]
}

# ============================================
# JWT Layer - PyJWT + cryptography (~8 MB compressed)
# Used by: Auth, Authorizer functions
# ============================================

resource "null_resource" "package_jwt_layer" {
  provisioner "local-exec" {
    command = <<EOT
      cd ${path.module}/../../../lambdas/layers/jwt && \
      rm -rf python && \
      mkdir python && \
      pip install -r requirements.txt -t python --platform manylinux2014_x86_64 --only-binary=:all: --python-version 3.11 && \
      zip -r layer.zip python
    EOT
  }

  triggers = {
    requirements = filemd5("${path.module}/../../../lambdas/layers/jwt/requirements.txt")
  }
}

resource "aws_lambda_layer_version" "jwt_layer" {
  filename            = "${path.module}/../../../lambdas/layers/jwt/layer.zip"
  layer_name          = "${var.environment}-jwt-dependencies"
  compatible_runtimes = ["python3.11"]
  description         = "JWT dependencies: PyJWT, cryptography"
  source_code_hash    = filebase64sha256("${path.module}/../../../lambdas/layers/jwt/layer.zip")
  
  depends_on = [null_resource.package_jwt_layer]
}

# ============================================
# SMS Layer - twilio (~10 MB compressed)
# Used by: SMS function only
# ============================================

resource "null_resource" "package_sms_layer" {
  provisioner "local-exec" {
    command = <<EOT
      cd ${path.module}/../../../lambdas/layers/sms && \
      rm -rf python && \
      mkdir python && \
      pip install -r requirements.txt -t python --platform manylinux2014_x86_64 --only-binary=:all: --python-version 3.11 && \
      zip -r layer.zip python
    EOT
  }

  triggers = {
    requirements = filemd5("${path.module}/../../../lambdas/layers/sms/requirements.txt")
  }
}

resource "aws_lambda_layer_version" "sms_layer" {
  filename            = "${path.module}/../../../lambdas/layers/sms/layer.zip"
  layer_name          = "${var.environment}-sms-dependencies"
  compatible_runtimes = ["python3.11"]
  description         = "SMS dependencies: twilio"
  source_code_hash    = filebase64sha256("${path.module}/../../../lambdas/layers/sms/layer.zip")
  
  depends_on = [null_resource.package_sms_layer]
}

# ============================================
# Outputs
# ============================================

output "core_layer_arn" {
  description = "ARN of the core dependencies layer"
  value       = aws_lambda_layer_version.core_layer.arn
}

output "jwt_layer_arn" {
  description = "ARN of the JWT dependencies layer"
  value       = aws_lambda_layer_version.jwt_layer.arn
}

output "sms_layer_arn" {
  description = "ARN of the SMS dependencies layer"
  value       = aws_lambda_layer_version.sms_layer.arn
}

# ============================================
# LangChain Layer - langchain + langgraph (~50 MB compressed)
# Used by: Chat function, Agent service
# ============================================

resource "null_resource" "package_langchain_layer" {
  provisioner "local-exec" {
    command = <<EOT
      cd ${path.module}/../../../lambdas/layers/langchain && \
      rm -rf python && \
      mkdir python && \
      pip install -r requirements.txt -t python --platform manylinux2014_x86_64 --only-binary=:all: --python-version 3.11 && \
      zip -r layer.zip python
    EOT
  }

  triggers = {
    requirements = filemd5("${path.module}/../../../lambdas/layers/langchain/requirements.txt")
  }
}

resource "aws_lambda_layer_version" "langchain_layer" {
  filename            = "${path.module}/../../../lambdas/layers/langchain/layer.zip"
  layer_name          = "${var.environment}-langchain-dependencies"
  compatible_runtimes = ["python3.11"]
  description         = "LangChain dependencies: langchain, langgraph, openai, posthog"
  source_code_hash    = filebase64sha256("${path.module}/../../../lambdas/layers/langchain/layer.zip")
  
  depends_on = [null_resource.package_langchain_layer]
}

output "langchain_layer_arn" {
  description = "ARN of the LangChain dependencies layer"
  value       = aws_lambda_layer_version.langchain_layer.arn
}

