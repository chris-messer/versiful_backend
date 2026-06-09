# REST Lambdas for the Bible Companion features (COMPANION_SPEC.md §14).
# Per-feature lambdas (definition + IAM via shared role + env + API Gateway routes).
# Handlers are minimal 501 stubs; feature teams fill in business logic later.
#
# Secrets: every companion lambda gets SECRET_ARN and uses the shared lambda role,
# which already carries secretsmanager:GetSecretValue scoped to the combined
# per-env secret (${env}-versiful_secrets). Lambdas read the Neon URL at runtime
# via get_secret('neon_database_url') -- never injected as a plaintext env var.
# The shared_dependencies layer bundles lambdas/shared/secrets_helper.py.
#
# CORS: the catch-all "OPTIONS /{proxy+}" route in _cors.tf covers preflight for
# every companion route, so no per-route OPTIONS routes are defined here.

locals {
  users_table_name = "${var.environment}-${var.project_name}-users"
}

# ============================================================================
# daily_verse -- GET /daily-verse (fetch the user's current daily verse for web)
# Note: daily verse is primarily a scheduled worker (see _companion_workers.tf);
# this read endpoint backs the web DailyVerseCard. Config lives on the users item.
# ============================================================================
data "archive_file" "daily_verse_zip" {
  type        = "zip"
  source_dir  = "${path.module}/../../../lambdas/daily_verse"
  output_path = "${path.module}/../../../lambdas/daily_verse/daily_verse.zip"
  excludes    = ["__pycache__", "*.pyc", "*.zip", ".pytest_cache", "*.egg-info"]
}

resource "aws_lambda_function" "daily_verse_function" {
  function_name    = "${var.environment}-${var.project_name}-daily-verse"
  handler          = "daily_verse_handler.handler"
  runtime          = "python3.11"
  role             = aws_iam_role.lambda_exec_role.arn
  filename         = data.archive_file.daily_verse_zip.output_path
  source_code_hash = data.archive_file.daily_verse_zip.output_base64sha256
  # langchain_layer supplies psycopg/Neon AND the shared modules so the read endpoint
  # can personalize from memories (recommended; spec §6). No twilio/stripe needed, so we
  # avoid the heavy shared_dependencies layer (kept this function under the 250 MB limit).
  layers = [
    aws_lambda_layer_version.langchain_layer.arn
  ]
  timeout = 30

  environment {
    variables = {
      ENVIRONMENT         = var.environment
      PROJECT_NAME        = var.project_name
      SECRET_ARN          = var.secret_arn
      USERS_TABLE         = local.users_table_name
      VERSE_HISTORY_TABLE = aws_dynamodb_table.verse_history.name
      CORS_ORIGIN         = var.allowed_cors_origins[0]
    }
  }

  tags = {
    Environment = var.environment
    Purpose     = "Companion daily verse API"
  }
}

resource "aws_lambda_permission" "daily_verse_permission" {
  statement_id  = "AllowAPIGatewayInvokeDailyVerse"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.daily_verse_function.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${var.apiGateway_execution_arn}/*/*"
  lifecycle {
    replace_triggered_by = [aws_lambda_function.daily_verse_function.id]
  }
}

resource "aws_apigatewayv2_integration" "daily_verse_integration" {
  api_id           = var.apiGateway_lambda_api_id
  integration_type = "AWS_PROXY"
  integration_uri  = aws_lambda_function.daily_verse_function.invoke_arn
}

resource "aws_apigatewayv2_route" "daily_verse_get" {
  api_id             = var.apiGateway_lambda_api_id
  route_key          = "GET /daily-verse"
  target             = "integrations/${aws_apigatewayv2_integration.daily_verse_integration.id}"
  authorization_type = "CUSTOM"
  authorizer_id      = var.jwt_auth_id
}

# ============================================================================
# prayers -- GET/POST /prayers, PUT/DELETE /prayers/{id}, POST /prayers/{id}/answered
# ============================================================================
data "archive_file" "prayers_zip" {
  type        = "zip"
  source_dir  = "${path.module}/../../../lambdas/prayers"
  output_path = "${path.module}/../../../lambdas/prayers/prayers.zip"
  excludes    = ["__pycache__", "*.pyc", "*.zip", ".pytest_cache", "*.egg-info"]
}

resource "aws_lambda_function" "prayers_function" {
  function_name    = "${var.environment}-${var.project_name}-prayers"
  handler          = "prayers_handler.handler"
  runtime          = "python3.11"
  role             = aws_iam_role.lambda_exec_role.arn
  filename         = data.archive_file.prayers_zip.output_path
  source_code_hash = data.archive_file.prayers_zip.output_base64sha256
  layers           = [aws_lambda_layer_version.shared_dependencies.arn]
  timeout          = 30

  environment {
    variables = {
      ENVIRONMENT   = var.environment
      PROJECT_NAME  = var.project_name
      SECRET_ARN    = var.secret_arn
      USERS_TABLE   = local.users_table_name
      PRAYERS_TABLE = aws_dynamodb_table.prayers.name
      CORS_ORIGIN   = var.allowed_cors_origins[0]
    }
  }

  tags = {
    Environment = var.environment
    Purpose     = "Companion prayers API"
  }
}

resource "aws_lambda_permission" "prayers_permission" {
  statement_id  = "AllowAPIGatewayInvokePrayers"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.prayers_function.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${var.apiGateway_execution_arn}/*/*"
  lifecycle {
    replace_triggered_by = [aws_lambda_function.prayers_function.id]
  }
}

resource "aws_apigatewayv2_integration" "prayers_integration" {
  api_id           = var.apiGateway_lambda_api_id
  integration_type = "AWS_PROXY"
  integration_uri  = aws_lambda_function.prayers_function.invoke_arn
}

resource "aws_apigatewayv2_route" "prayers_list" {
  api_id             = var.apiGateway_lambda_api_id
  route_key          = "GET /prayers"
  target             = "integrations/${aws_apigatewayv2_integration.prayers_integration.id}"
  authorization_type = "CUSTOM"
  authorizer_id      = var.jwt_auth_id
}

resource "aws_apigatewayv2_route" "prayers_create" {
  api_id             = var.apiGateway_lambda_api_id
  route_key          = "POST /prayers"
  target             = "integrations/${aws_apigatewayv2_integration.prayers_integration.id}"
  authorization_type = "CUSTOM"
  authorizer_id      = var.jwt_auth_id
}

resource "aws_apigatewayv2_route" "prayers_update" {
  api_id             = var.apiGateway_lambda_api_id
  route_key          = "PUT /prayers/{id}"
  target             = "integrations/${aws_apigatewayv2_integration.prayers_integration.id}"
  authorization_type = "CUSTOM"
  authorizer_id      = var.jwt_auth_id
}

resource "aws_apigatewayv2_route" "prayers_answered" {
  api_id             = var.apiGateway_lambda_api_id
  route_key          = "POST /prayers/{id}/answered"
  target             = "integrations/${aws_apigatewayv2_integration.prayers_integration.id}"
  authorization_type = "CUSTOM"
  authorizer_id      = var.jwt_auth_id
}

resource "aws_apigatewayv2_route" "prayers_delete" {
  api_id             = var.apiGateway_lambda_api_id
  route_key          = "DELETE /prayers/{id}"
  target             = "integrations/${aws_apigatewayv2_integration.prayers_integration.id}"
  authorization_type = "CUSTOM"
  authorizer_id      = var.jwt_auth_id
}

# ============================================================================
# reflections -- GET/POST /reflections, DELETE /reflections/{id}  (Neon-backed)
# ============================================================================
data "archive_file" "reflections_zip" {
  type        = "zip"
  source_dir  = "${path.module}/../../../lambdas/reflections"
  output_path = "${path.module}/../../../lambdas/reflections/reflections.zip"
  excludes    = ["__pycache__", "*.pyc", "*.zip", ".pytest_cache", "*.egg-info"]
}

resource "aws_lambda_function" "reflections_function" {
  function_name    = "${var.environment}-${var.project_name}-reflections"
  handler          = "reflections_handler.handler"
  runtime          = "python3.11"
  role             = aws_iam_role.lambda_exec_role.arn
  filename         = data.archive_file.reflections_zip.output_path
  source_code_hash = data.archive_file.reflections_zip.output_base64sha256
  # langchain_layer supplies psycopg (and the shared modules) so the Neon-backed
  # reflections endpoints work. REQUIRED — without it every endpoint 503s (spec §8).
  # No twilio/stripe needed, so shared_dependencies is intentionally not mounted.
  layers = [
    aws_lambda_layer_version.langchain_layer.arn
  ]
  timeout = 30

  environment {
    variables = {
      ENVIRONMENT  = var.environment
      PROJECT_NAME = var.project_name
      SECRET_ARN   = var.secret_arn
      USERS_TABLE  = local.users_table_name
      CORS_ORIGIN  = var.allowed_cors_origins[0]
    }
  }

  tags = {
    Environment = var.environment
    Purpose     = "Companion reflections API - Neon"
  }
}

resource "aws_lambda_permission" "reflections_permission" {
  statement_id  = "AllowAPIGatewayInvokeReflections"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.reflections_function.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${var.apiGateway_execution_arn}/*/*"
  lifecycle {
    replace_triggered_by = [aws_lambda_function.reflections_function.id]
  }
}

resource "aws_apigatewayv2_integration" "reflections_integration" {
  api_id           = var.apiGateway_lambda_api_id
  integration_type = "AWS_PROXY"
  integration_uri  = aws_lambda_function.reflections_function.invoke_arn
}

resource "aws_apigatewayv2_route" "reflections_list" {
  api_id             = var.apiGateway_lambda_api_id
  route_key          = "GET /reflections"
  target             = "integrations/${aws_apigatewayv2_integration.reflections_integration.id}"
  authorization_type = "CUSTOM"
  authorizer_id      = var.jwt_auth_id
}

resource "aws_apigatewayv2_route" "reflections_create" {
  api_id             = var.apiGateway_lambda_api_id
  route_key          = "POST /reflections"
  target             = "integrations/${aws_apigatewayv2_integration.reflections_integration.id}"
  authorization_type = "CUSTOM"
  authorizer_id      = var.jwt_auth_id
}

resource "aws_apigatewayv2_route" "reflections_delete" {
  api_id             = var.apiGateway_lambda_api_id
  route_key          = "DELETE /reflections/{id}"
  target             = "integrations/${aws_apigatewayv2_integration.reflections_integration.id}"
  authorization_type = "CUSTOM"
  authorizer_id      = var.jwt_auth_id
}

# ============================================================================
# plans -- catalog (public) + enrollment/progress (authed). COMPANION_SPEC.md §14.
# ============================================================================
data "archive_file" "plans_zip" {
  type        = "zip"
  source_dir  = "${path.module}/../../../lambdas/plans"
  output_path = "${path.module}/../../../lambdas/plans/plans.zip"
  excludes    = ["__pycache__", "*.pyc", "*.zip", ".pytest_cache", "*.egg-info"]
}

resource "aws_lambda_function" "plans_function" {
  function_name    = "${var.environment}-${var.project_name}-plans"
  handler          = "plans_handler.handler"
  runtime          = "python3.11"
  role             = aws_iam_role.lambda_exec_role.arn
  filename         = data.archive_file.plans_zip.output_path
  source_code_hash = data.archive_file.plans_zip.output_base64sha256
  layers           = [aws_lambda_layer_version.shared_dependencies.arn]
  timeout          = 30

  environment {
    variables = {
      ENVIRONMENT                       = var.environment
      PROJECT_NAME                      = var.project_name
      SECRET_ARN                        = var.secret_arn
      USERS_TABLE                      = local.users_table_name
      READING_PLANS_TABLE              = aws_dynamodb_table.reading_plans.name
      READING_PLAN_DAYS_TABLE          = aws_dynamodb_table.reading_plan_days.name
      USER_READING_PLANS_TABLE         = aws_dynamodb_table.user_reading_plans.name
      USER_READING_PLAN_PROGRESS_TABLE = aws_dynamodb_table.user_reading_plan_progress.name
      CORS_ORIGIN                      = var.allowed_cors_origins[0]
    }
  }

  tags = {
    Environment = var.environment
    Purpose     = "Companion reading plans API"
  }
}

resource "aws_lambda_permission" "plans_permission" {
  statement_id  = "AllowAPIGatewayInvokePlans"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.plans_function.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${var.apiGateway_execution_arn}/*/*"
  lifecycle {
    replace_triggered_by = [aws_lambda_function.plans_function.id]
  }
}

resource "aws_apigatewayv2_integration" "plans_integration" {
  api_id           = var.apiGateway_lambda_api_id
  integration_type = "AWS_PROXY"
  integration_uri  = aws_lambda_function.plans_function.invoke_arn
}

# Catalog routes are public (spec §14: "public ok").
resource "aws_apigatewayv2_route" "plans_catalog" {
  api_id    = var.apiGateway_lambda_api_id
  route_key = "GET /plans"
  target    = "integrations/${aws_apigatewayv2_integration.plans_integration.id}"
}

resource "aws_apigatewayv2_route" "plans_detail" {
  api_id    = var.apiGateway_lambda_api_id
  route_key = "GET /plans/{slug}"
  target    = "integrations/${aws_apigatewayv2_integration.plans_integration.id}"
}

resource "aws_apigatewayv2_route" "plans_enroll" {
  api_id             = var.apiGateway_lambda_api_id
  route_key          = "POST /plans/{slug}/enroll"
  target             = "integrations/${aws_apigatewayv2_integration.plans_integration.id}"
  authorization_type = "CUSTOM"
  authorizer_id      = var.jwt_auth_id
}

resource "aws_apigatewayv2_route" "plans_enrolled_list" {
  api_id             = var.apiGateway_lambda_api_id
  route_key          = "GET /plans/enrolled"
  target             = "integrations/${aws_apigatewayv2_integration.plans_integration.id}"
  authorization_type = "CUSTOM"
  authorizer_id      = var.jwt_auth_id
}

resource "aws_apigatewayv2_route" "plans_complete_day" {
  api_id             = var.apiGateway_lambda_api_id
  route_key          = "POST /plans/enrolled/{id}/complete-day"
  target             = "integrations/${aws_apigatewayv2_integration.plans_integration.id}"
  authorization_type = "CUSTOM"
  authorizer_id      = var.jwt_auth_id
}

resource "aws_apigatewayv2_route" "plans_pause" {
  api_id             = var.apiGateway_lambda_api_id
  route_key          = "POST /plans/enrolled/{id}/pause"
  target             = "integrations/${aws_apigatewayv2_integration.plans_integration.id}"
  authorization_type = "CUSTOM"
  authorizer_id      = var.jwt_auth_id
}

# ============================================================================
# checkins -- GET /checkins (upcoming/recent check-ins transparency view, §10.7)
# ============================================================================
data "archive_file" "checkins_zip" {
  type        = "zip"
  source_dir  = "${path.module}/../../../lambdas/checkins"
  output_path = "${path.module}/../../../lambdas/checkins/checkins.zip"
  excludes    = ["__pycache__", "*.pyc", "*.zip", ".pytest_cache", "*.egg-info"]
}

resource "aws_lambda_function" "checkins_function" {
  function_name    = "${var.environment}-${var.project_name}-checkins"
  handler          = "checkins_handler.handler"
  runtime          = "python3.11"
  role             = aws_iam_role.lambda_exec_role.arn
  filename         = data.archive_file.checkins_zip.output_path
  source_code_hash = data.archive_file.checkins_zip.output_base64sha256
  layers           = [aws_lambda_layer_version.shared_dependencies.arn]
  timeout          = 30

  environment {
    variables = {
      ENVIRONMENT    = var.environment
      PROJECT_NAME   = var.project_name
      SECRET_ARN     = var.secret_arn
      USERS_TABLE    = local.users_table_name
      CHECKINS_TABLE = aws_dynamodb_table.checkins.name
      CORS_ORIGIN    = var.allowed_cors_origins[0]
    }
  }

  tags = {
    Environment = var.environment
    Purpose     = "Companion check-ins API"
  }
}

resource "aws_lambda_permission" "checkins_permission" {
  statement_id  = "AllowAPIGatewayInvokeCheckins"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.checkins_function.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${var.apiGateway_execution_arn}/*/*"
  lifecycle {
    replace_triggered_by = [aws_lambda_function.checkins_function.id]
  }
}

resource "aws_apigatewayv2_integration" "checkins_integration" {
  api_id           = var.apiGateway_lambda_api_id
  integration_type = "AWS_PROXY"
  integration_uri  = aws_lambda_function.checkins_function.invoke_arn
}

resource "aws_apigatewayv2_route" "checkins_list" {
  api_id             = var.apiGateway_lambda_api_id
  route_key          = "GET /checkins"
  target             = "integrations/${aws_apigatewayv2_integration.checkins_integration.id}"
  authorization_type = "CUSTOM"
  authorizer_id      = var.jwt_auth_id
}

# ============================================================================
# walk -- GET /walk/summary + memory controls (GET/DELETE /walk/memories[/{id}])
# Aggregates DynamoDB companion tables + Neon (memories/reflections). §11, §11.2a.
# ============================================================================
data "archive_file" "walk_zip" {
  type        = "zip"
  source_dir  = "${path.module}/../../../lambdas/walk"
  output_path = "${path.module}/../../../lambdas/walk/walk.zip"
  excludes    = ["__pycache__", "*.pyc", "*.zip", ".pytest_cache", "*.egg-info"]
}

resource "aws_lambda_function" "walk_function" {
  function_name    = "${var.environment}-${var.project_name}-walk"
  handler          = "walk_handler.handler"
  runtime          = "python3.11"
  role             = aws_iam_role.lambda_exec_role.arn
  filename         = data.archive_file.walk_zip.output_path
  source_code_hash = data.archive_file.walk_zip.output_base64sha256
  # langchain_layer supplies psycopg (and the shared modules) for the Neon memory
  # list/delete/summary controls. REQUIRED for the memory endpoints (spec §11.2a).
  # No twilio/stripe needed, so shared_dependencies is intentionally not mounted.
  layers = [
    aws_lambda_layer_version.langchain_layer.arn
  ]
  timeout = 30

  environment {
    variables = {
      ENVIRONMENT              = var.environment
      PROJECT_NAME             = var.project_name
      SECRET_ARN               = var.secret_arn
      USERS_TABLE              = local.users_table_name
      PRAYERS_TABLE            = aws_dynamodb_table.prayers.name
      VERSE_HISTORY_TABLE      = aws_dynamodb_table.verse_history.name
      CHECKINS_TABLE           = aws_dynamodb_table.checkins.name
      USER_READING_PLANS_TABLE = aws_dynamodb_table.user_reading_plans.name
      CORS_ORIGIN              = var.allowed_cors_origins[0]
    }
  }

  tags = {
    Environment = var.environment
    Purpose     = "Companion My Walk / journey API"
  }
}

resource "aws_lambda_permission" "walk_permission" {
  statement_id  = "AllowAPIGatewayInvokeWalk"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.walk_function.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${var.apiGateway_execution_arn}/*/*"
  lifecycle {
    replace_triggered_by = [aws_lambda_function.walk_function.id]
  }
}

resource "aws_apigatewayv2_integration" "walk_integration" {
  api_id           = var.apiGateway_lambda_api_id
  integration_type = "AWS_PROXY"
  integration_uri  = aws_lambda_function.walk_function.invoke_arn
}

resource "aws_apigatewayv2_route" "walk_summary" {
  api_id             = var.apiGateway_lambda_api_id
  route_key          = "GET /walk/summary"
  target             = "integrations/${aws_apigatewayv2_integration.walk_integration.id}"
  authorization_type = "CUSTOM"
  authorizer_id      = var.jwt_auth_id
}

resource "aws_apigatewayv2_route" "walk_memories_list" {
  api_id             = var.apiGateway_lambda_api_id
  route_key          = "GET /walk/memories"
  target             = "integrations/${aws_apigatewayv2_integration.walk_integration.id}"
  authorization_type = "CUSTOM"
  authorizer_id      = var.jwt_auth_id
}

resource "aws_apigatewayv2_route" "walk_memories_clear" {
  api_id             = var.apiGateway_lambda_api_id
  route_key          = "DELETE /walk/memories"
  target             = "integrations/${aws_apigatewayv2_integration.walk_integration.id}"
  authorization_type = "CUSTOM"
  authorizer_id      = var.jwt_auth_id
}

resource "aws_apigatewayv2_route" "walk_memory_delete" {
  api_id             = var.apiGateway_lambda_api_id
  route_key          = "DELETE /walk/memories/{id}"
  target             = "integrations/${aws_apigatewayv2_integration.walk_integration.id}"
  authorization_type = "CUSTOM"
  authorizer_id      = var.jwt_auth_id
}

# ============================================================================
# account_management -- GET/PUT /users/preferences (comms-pref attrs on users item)
# Spec §14 lists these routes; §5.4/§12 note the attributes live on the users item.
# ============================================================================
data "archive_file" "account_management_zip" {
  type        = "zip"
  source_dir  = "${path.module}/../../../lambdas/account_management"
  output_path = "${path.module}/../../../lambdas/account_management/account_management.zip"
  excludes    = ["__pycache__", "*.pyc", "*.zip", ".pytest_cache", "*.egg-info"]
}

resource "aws_lambda_function" "account_management_function" {
  function_name    = "${var.environment}-${var.project_name}-account-management"
  handler          = "account_management_handler.handler"
  runtime          = "python3.11"
  role             = aws_iam_role.lambda_exec_role.arn
  filename         = data.archive_file.account_management_zip.output_path
  source_code_hash = data.archive_file.account_management_zip.output_base64sha256
  layers           = [aws_lambda_layer_version.shared_dependencies.arn]
  timeout          = 30

  environment {
    variables = {
      ENVIRONMENT  = var.environment
      PROJECT_NAME = var.project_name
      SECRET_ARN   = var.secret_arn
      USERS_TABLE  = local.users_table_name
      CORS_ORIGIN  = var.allowed_cors_origins[0]
    }
  }

  tags = {
    Environment = var.environment
    Purpose     = "Companion account-management / preferences API"
  }
}

resource "aws_lambda_permission" "account_management_permission" {
  statement_id  = "AllowAPIGatewayInvokeAccountMgmt"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.account_management_function.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${var.apiGateway_execution_arn}/*/*"
  lifecycle {
    replace_triggered_by = [aws_lambda_function.account_management_function.id]
  }
}

resource "aws_apigatewayv2_integration" "account_management_integration" {
  api_id           = var.apiGateway_lambda_api_id
  integration_type = "AWS_PROXY"
  integration_uri  = aws_lambda_function.account_management_function.invoke_arn
}

resource "aws_apigatewayv2_route" "preferences_get" {
  api_id             = var.apiGateway_lambda_api_id
  route_key          = "GET /users/preferences"
  target             = "integrations/${aws_apigatewayv2_integration.account_management_integration.id}"
  authorization_type = "CUSTOM"
  authorizer_id      = var.jwt_auth_id
}

resource "aws_apigatewayv2_route" "preferences_put" {
  api_id             = var.apiGateway_lambda_api_id
  route_key          = "PUT /users/preferences"
  target             = "integrations/${aws_apigatewayv2_integration.account_management_integration.id}"
  authorization_type = "CUSTOM"
  authorizer_id      = var.jwt_auth_id
}
