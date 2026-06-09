# DynamoDB tables for the Bible Companion features (COMPANION_SPEC.md §4.3).
# DynamoDB attribute/key/GSI names are camelCase (ADR-1 in COMPANION_BUILD_PLAN.md).
# Neon (Postgres) holds user_memories + reflections only -- not modeled here.

# prayers -- private, living prayer list (spec §4.3, §7).
# Access pattern: Query PK=userId, filter by status in-app (no status GSI needed).
resource "aws_dynamodb_table" "prayers" {
  name         = "${var.environment}-${var.project_name}-prayers"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "userId"
  range_key    = "prayerId"

  attribute {
    name = "userId"
    type = "S"
  }

  attribute {
    name = "prayerId"
    type = "S"
  }

  tags = {
    Environment = var.environment
    Purpose     = "Companion prayer journal"
  }
}

# verse_history -- every verse surfaced; powers daily-verse relevance + non-duplication (spec §4.3, §6).
# Access pattern: Query PK=userId, ScanIndexForward=false for the do-not-repeat list.
# phoneNumber-index supports pre-registration SMS verses (before a userId exists),
# reconciled to userId on registration (spec §4.3 note).
resource "aws_dynamodb_table" "verse_history" {
  name         = "${var.environment}-${var.project_name}-verse-history"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "userId"
  range_key    = "sentAt"

  attribute {
    name = "userId"
    type = "S"
  }

  attribute {
    name = "sentAt"
    type = "S"
  }

  attribute {
    name = "phoneNumber"
    type = "S"
  }

  global_secondary_index {
    name            = "phoneNumber-index"
    hash_key        = "phoneNumber"
    range_key       = "sentAt"
    projection_type = "ALL"
  }

  tags = {
    Environment = var.environment
    Purpose     = "Companion verse history"
  }
}

# checkins -- proactive outreach scheduling + log (spec §4.3, §10).
# checkins_by_status GSI drives the secondary, capped time-sensitive due-date pass:
# Query status = 'scheduled' AND scheduledFor <= now (spec §10.5).
resource "aws_dynamodb_table" "checkins" {
  name         = "${var.environment}-${var.project_name}-checkins"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "userId"
  range_key    = "checkinId"

  attribute {
    name = "userId"
    type = "S"
  }

  attribute {
    name = "checkinId"
    type = "S"
  }

  attribute {
    name = "status"
    type = "S"
  }

  attribute {
    name = "scheduledFor"
    type = "S"
  }

  global_secondary_index {
    name            = "checkins_by_status"
    hash_key        = "status"
    range_key       = "scheduledFor"
    projection_type = "ALL"
  }

  tags = {
    Environment = var.environment
    Purpose     = "Companion proactive check-ins"
  }
}

# reading_plans -- plan catalog (spec §4.3, §9). PK=slug, no sort key.
resource "aws_dynamodb_table" "reading_plans" {
  name         = "${var.environment}-${var.project_name}-reading-plans"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "slug"

  attribute {
    name = "slug"
    type = "S"
  }

  tags = {
    Environment = var.environment
    Purpose     = "Companion reading plan catalog"
  }
}

# reading_plan_days -- catalog day content (spec §4.3, §9). PK=slug, SK=dayNumber (numeric).
resource "aws_dynamodb_table" "reading_plan_days" {
  name         = "${var.environment}-${var.project_name}-reading-plan-days"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "slug"
  range_key    = "dayNumber"

  attribute {
    name = "slug"
    type = "S"
  }

  attribute {
    name = "dayNumber"
    type = "N"
  }

  tags = {
    Environment = var.environment
    Purpose     = "Companion reading plan day content"
  }
}

# user_reading_plans -- per-user enrollment (spec §4.3, §9). PK=userId, SK=planId.
resource "aws_dynamodb_table" "user_reading_plans" {
  name         = "${var.environment}-${var.project_name}-user-reading-plans"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "userId"
  range_key    = "planId"

  attribute {
    name = "userId"
    type = "S"
  }

  attribute {
    name = "planId"
    type = "S"
  }

  tags = {
    Environment = var.environment
    Purpose     = "Companion user reading plan enrollment"
  }
}

# user_reading_plan_progress -- per-user per-day progress (spec §4.3, §9).
# PK=userId, SK holds the composite "planId#dayNumber" value (attribute named dayKey).
resource "aws_dynamodb_table" "user_reading_plan_progress" {
  name         = "${var.environment}-${var.project_name}-user-reading-plan-progress"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "userId"
  range_key    = "dayKey"

  attribute {
    name = "userId"
    type = "S"
  }

  attribute {
    name = "dayKey"
    type = "S"
  }

  tags = {
    Environment = var.environment
    Purpose     = "Companion user reading plan progress"
  }
}

# IAM: allow the shared lambda execution role to read/write the new companion
# tables and their GSIs (mirrors the chat_dynamodb_access pattern in main.tf).
resource "aws_iam_policy" "companion_dynamodb_access" {
  name        = "${var.environment}-${var.project_name}-companion-dynamodb-access"
  description = "Allow Lambda to access companion DynamoDB tables"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "dynamodb:GetItem",
          "dynamodb:PutItem",
          "dynamodb:UpdateItem",
          "dynamodb:DeleteItem",
          "dynamodb:BatchGetItem",
          "dynamodb:BatchWriteItem",
          "dynamodb:Query",
          "dynamodb:Scan"
        ]
        Resource = [
          aws_dynamodb_table.prayers.arn,
          "${aws_dynamodb_table.prayers.arn}/*",
          aws_dynamodb_table.verse_history.arn,
          "${aws_dynamodb_table.verse_history.arn}/*",
          aws_dynamodb_table.checkins.arn,
          "${aws_dynamodb_table.checkins.arn}/*",
          aws_dynamodb_table.reading_plans.arn,
          "${aws_dynamodb_table.reading_plans.arn}/*",
          aws_dynamodb_table.reading_plan_days.arn,
          "${aws_dynamodb_table.reading_plan_days.arn}/*",
          aws_dynamodb_table.user_reading_plans.arn,
          "${aws_dynamodb_table.user_reading_plans.arn}/*",
          aws_dynamodb_table.user_reading_plan_progress.arn,
          "${aws_dynamodb_table.user_reading_plan_progress.arn}/*"
        ]
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "attach_companion_dynamodb_policy" {
  role       = aws_iam_role.lambda_exec_role.name
  policy_arn = aws_iam_policy.companion_dynamodb_access.arn
}

# Outputs for the companion tables
output "prayers_table_name" {
  description = "Name of the prayers DynamoDB table"
  value       = aws_dynamodb_table.prayers.name
}

output "verse_history_table_name" {
  description = "Name of the verse_history DynamoDB table"
  value       = aws_dynamodb_table.verse_history.name
}

output "checkins_table_name" {
  description = "Name of the checkins DynamoDB table"
  value       = aws_dynamodb_table.checkins.name
}

output "reading_plans_table_name" {
  description = "Name of the reading_plans catalog DynamoDB table"
  value       = aws_dynamodb_table.reading_plans.name
}

output "reading_plan_days_table_name" {
  description = "Name of the reading_plan_days catalog DynamoDB table"
  value       = aws_dynamodb_table.reading_plan_days.name
}

output "user_reading_plans_table_name" {
  description = "Name of the user_reading_plans DynamoDB table"
  value       = aws_dynamodb_table.user_reading_plans.name
}

output "user_reading_plan_progress_table_name" {
  description = "Name of the user_reading_plan_progress DynamoDB table"
  value       = aws_dynamodb_table.user_reading_plan_progress.name
}
