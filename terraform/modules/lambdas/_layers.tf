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

# The langchain layer also vendors the lightweight shared Python modules
# (secrets_helper, neon/memory modules, promoted agent-tool modules). This lets the
# langchain-using functions (chat, companion read endpoints + workers) get both their
# heavy deps (openai/langgraph/psycopg/pydantic) AND the shared modules from ONE layer,
# instead of also mounting the full shared_dependencies layer (twilio/stripe/cryptography),
# which double-counted toward the 250 MB unzipped limit and broke the dev apply.
resource "null_resource" "package_langchain_layer" {
  provisioner "local-exec" {
    command = <<EOT
      cd ${path.module}/../../../lambdas/layers/langchain && \
      rm -rf python && \
      mkdir python && \
      pip install -r requirements.txt -t python --platform manylinux2014_x86_64 --only-binary=:all: --python-version 3.11 && \
      cp ../../shared/*.py python/ && \
      zip -r layer.zip python
    EOT
  }

  triggers = {
    requirements       = filemd5("${path.module}/../../../lambdas/layers/langchain/requirements.txt")
    shared_secrets     = filemd5("${path.module}/../../../lambdas/shared/secrets_helper.py")
    shared_sms         = filemd5("${path.module}/../../../lambdas/shared/sms_notifications.py")
    shared_neon        = filemd5("${path.module}/../../../lambdas/shared/neon_client.py")
    shared_embeddings  = filemd5("${path.module}/../../../lambdas/shared/embeddings.py")
    shared_mem_store   = filemd5("${path.module}/../../../lambdas/shared/memory_store.py")
    shared_mem_recall  = filemd5("${path.module}/../../../lambdas/shared/memory_retrieval.py")
    shared_mem_extract = filemd5("${path.module}/../../../lambdas/shared/memory_extractor.py")
    shared_preferences = filemd5("${path.module}/../../../lambdas/shared/preferences.py")
    shared_account     = filemd5("${path.module}/../../../lambdas/shared/account_tools.py")
    shared_prayer      = filemd5("${path.module}/../../../lambdas/shared/prayer_tools.py")
    shared_reflect     = filemd5("${path.module}/../../../lambdas/shared/reflection_tools.py")
    shared_plans_repo  = filemd5("${path.module}/../../../lambdas/shared/reading_plans_repo.py")
  }
}

resource "aws_lambda_layer_version" "langchain_layer" {
  filename            = "${path.module}/../../../lambdas/layers/langchain/layer.zip"
  layer_name          = "${var.environment}-langchain-dependencies"
  compatible_runtimes = ["python3.11"]
  description         = "LangChain dependencies: langchain, langgraph, openai"
  
  depends_on = [null_resource.package_langchain_layer]
}

output "langchain_layer_arn" {
  description = "ARN of the LangChain dependencies layer"
  value       = aws_lambda_layer_version.langchain_layer.arn
}

