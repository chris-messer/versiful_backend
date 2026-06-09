# Scheduled worker Lambdas for the Bible Companion features (COMPANION_SPEC.md §15.2).
# Triggered by EventBridge Scheduler. Handlers are minimal stubs; feature teams
# fill in business logic later.
#
# Secrets/Neon: workers use the shared lambda role (secretsmanager:GetSecretValue
# already attached) and read the Neon URL at runtime via get_secret('neon_database_url').
# Each worker mounts sms_layer (twilio) + langchain_layer (openai/langgraph/psycopg +
# the vendored shared modules), so it can read secrets, call the LLM, and send SMS.

# ----------------------------------------------------------------------------
# EventBridge Scheduler execution role -- lets the schedules invoke the workers.
# ----------------------------------------------------------------------------
resource "aws_iam_role" "companion_scheduler_role" {
  name = "${var.environment}-${var.project_name}-companion-scheduler-role"
  tags = {
    Environment = var.environment
  }
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect    = "Allow"
        Principal = { Service = "scheduler.amazonaws.com" }
        Action    = "sts:AssumeRole"
      }
    ]
  })
}

resource "aws_iam_policy" "companion_scheduler_invoke" {
  name        = "${var.environment}-${var.project_name}-companion-scheduler-invoke"
  description = "Allow EventBridge Scheduler to invoke the companion worker lambdas"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = ["lambda:InvokeFunction"]
        Resource = [
          aws_lambda_function.daily_verse_worker.arn,
          "${aws_lambda_function.daily_verse_worker.arn}:*",
          aws_lambda_function.reading_plan_delivery.arn,
          "${aws_lambda_function.reading_plan_delivery.arn}:*",
          aws_lambda_function.checkin_dispatcher.arn,
          "${aws_lambda_function.checkin_dispatcher.arn}:*",
          aws_lambda_function.prayer_reminder.arn,
          "${aws_lambda_function.prayer_reminder.arn}:*"
        ]
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "attach_companion_scheduler_invoke" {
  role       = aws_iam_role.companion_scheduler_role.name
  policy_arn = aws_iam_policy.companion_scheduler_invoke.arn
}

# ----------------------------------------------------------------------------
# daily_verse_worker -- selects due daily-verse users, sends + records (§6, §15.2)
# ----------------------------------------------------------------------------
data "archive_file" "daily_verse_worker_zip" {
  type        = "zip"
  source_dir  = "${path.module}/../../../lambdas/daily_verse_worker"
  output_path = "${path.module}/../../../lambdas/daily_verse_worker/daily_verse_worker.zip"
  excludes    = ["__pycache__", "*.pyc", "*.zip", ".pytest_cache", "*.egg-info"]
}

resource "aws_lambda_function" "daily_verse_worker" {
  function_name    = "${var.environment}-${var.project_name}-daily-verse-worker"
  handler          = "daily_verse_worker_handler.handler"
  runtime          = "python3.11"
  role             = aws_iam_role.lambda_exec_role.arn
  filename         = data.archive_file.daily_verse_worker_zip.output_path
  source_code_hash = data.archive_file.daily_verse_worker_zip.output_base64sha256
  # sms_layer supplies twilio for send_sms; langchain_layer supplies openai/psycopg +
  # the shared modules (sms_notifications/verse_engine deps). We deliberately avoid the
  # heavy shared_dependencies layer here — stacking it on langchain exceeded the 250 MB
  # unzipped Lambda limit. twilio is the only thing these workers needed from it.
  layers = [
    aws_lambda_layer_version.sms_layer.arn,
    aws_lambda_layer_version.langchain_layer.arn
  ]
  timeout     = 120
  memory_size = 512

  environment {
    variables = {
      ENVIRONMENT         = var.environment
      PROJECT_NAME        = var.project_name
      SECRET_ARN          = var.secret_arn
      USERS_TABLE         = local.users_table_name
      VERSE_HISTORY_TABLE = aws_dynamodb_table.verse_history.name
      VERSIFUL_PHONE      = var.versiful_phone
      POSTHOG_API_KEY     = var.posthog_apikey
      # Fallback timezone for users without a stored tz when bucketing the 15-min run.
      DEFAULT_TIMEZONE = "America/New_York"
    }
  }

  tags = {
    Environment = var.environment
    Purpose     = "Companion daily verse scheduled worker"
  }
}

resource "aws_scheduler_schedule" "daily_verse_worker_schedule" {
  name = "${var.environment}-${var.project_name}-daily-verse-worker"

  flexible_time_window {
    mode = "OFF"
  }

  # Every 15 minutes, timezone-bucketed selection happens inside the worker (§6, §15.2).
  schedule_expression          = "rate(15 minutes)"
  schedule_expression_timezone = "UTC"

  target {
    arn      = aws_lambda_function.daily_verse_worker.arn
    role_arn = aws_iam_role.companion_scheduler_role.arn
  }
}

# ----------------------------------------------------------------------------
# reading_plan_delivery -- delivers due plan days to enrolled users (§9, §15.2)
# ----------------------------------------------------------------------------
data "archive_file" "reading_plan_delivery_zip" {
  type        = "zip"
  source_dir  = "${path.module}/../../../lambdas/reading_plan_delivery"
  output_path = "${path.module}/../../../lambdas/reading_plan_delivery/reading_plan_delivery.zip"
  excludes    = ["__pycache__", "*.pyc", "*.zip", ".pytest_cache", "*.egg-info"]
}

resource "aws_lambda_function" "reading_plan_delivery" {
  function_name    = "${var.environment}-${var.project_name}-reading-plan-delivery"
  handler          = "reading_plan_delivery_handler.handler"
  runtime          = "python3.11"
  role             = aws_iam_role.lambda_exec_role.arn
  filename         = data.archive_file.reading_plan_delivery_zip.output_path
  source_code_hash = data.archive_file.reading_plan_delivery_zip.output_base64sha256
  # sms_layer supplies twilio for send_sms; langchain_layer supplies openai/psycopg +
  # the shared modules. Avoids the heavy shared_dependencies layer (250 MB limit).
  layers = [
    aws_lambda_layer_version.sms_layer.arn,
    aws_lambda_layer_version.langchain_layer.arn
  ]
  timeout     = 120
  memory_size = 512

  environment {
    variables = {
      ENVIRONMENT                      = var.environment
      PROJECT_NAME                     = var.project_name
      SECRET_ARN                       = var.secret_arn
      USERS_TABLE                      = local.users_table_name
      READING_PLANS_TABLE              = aws_dynamodb_table.reading_plans.name
      READING_PLAN_DAYS_TABLE          = aws_dynamodb_table.reading_plan_days.name
      USER_READING_PLANS_TABLE         = aws_dynamodb_table.user_reading_plans.name
      USER_READING_PLAN_PROGRESS_TABLE = aws_dynamodb_table.user_reading_plan_progress.name
      VERSE_HISTORY_TABLE              = aws_dynamodb_table.verse_history.name
      VERSIFUL_PHONE                   = var.versiful_phone
      POSTHOG_API_KEY                  = var.posthog_apikey
      DEFAULT_TIMEZONE                 = "America/New_York"
    }
  }

  tags = {
    Environment = var.environment
    Purpose     = "Companion reading plan delivery scheduled worker"
  }
}

resource "aws_scheduler_schedule" "reading_plan_delivery_schedule" {
  name = "${var.environment}-${var.project_name}-reading-plan-delivery"

  flexible_time_window {
    mode = "OFF"
  }

  schedule_expression          = "rate(15 minutes)"
  schedule_expression_timezone = "UTC"

  target {
    arn      = aws_lambda_function.reading_plan_delivery.arn
    role_arn = aws_iam_role.companion_scheduler_role.arn
  }
}

# ----------------------------------------------------------------------------
# checkin_dispatcher -- hourly; inactivity scan + capped due-date pass (§10, §15.2)
# ----------------------------------------------------------------------------
data "archive_file" "checkin_dispatcher_zip" {
  type        = "zip"
  source_dir  = "${path.module}/../../../lambdas/checkin_dispatcher"
  output_path = "${path.module}/../../../lambdas/checkin_dispatcher/checkin_dispatcher.zip"
  excludes    = ["__pycache__", "*.pyc", "*.zip", ".pytest_cache", "*.egg-info"]
}

resource "aws_lambda_function" "checkin_dispatcher" {
  function_name    = "${var.environment}-${var.project_name}-checkin-dispatcher"
  handler          = "checkin_dispatcher_handler.handler"
  runtime          = "python3.11"
  role             = aws_iam_role.lambda_exec_role.arn
  filename         = data.archive_file.checkin_dispatcher_zip.output_path
  source_code_hash = data.archive_file.checkin_dispatcher_zip.output_base64sha256
  # sms_layer supplies twilio for send_sms; langchain_layer supplies openai/psycopg +
  # the shared modules. Avoids the heavy shared_dependencies layer (250 MB limit).
  layers = [
    aws_lambda_layer_version.sms_layer.arn,
    aws_lambda_layer_version.langchain_layer.arn
  ]
  timeout     = 300
  memory_size = 512

  environment {
    variables = {
      ENVIRONMENT              = var.environment
      PROJECT_NAME             = var.project_name
      SECRET_ARN               = var.secret_arn
      USERS_TABLE              = local.users_table_name
      CHECKINS_TABLE           = aws_dynamodb_table.checkins.name
      PRAYERS_TABLE            = aws_dynamodb_table.prayers.name
      VERSE_HISTORY_TABLE      = aws_dynamodb_table.verse_history.name
      USER_READING_PLANS_TABLE = aws_dynamodb_table.user_reading_plans.name
      VERSIFUL_PHONE           = var.versiful_phone
      POSTHOG_API_KEY          = var.posthog_apikey
      DEFAULT_TIMEZONE         = "America/New_York"
      # Safety cap on the secondary time-sensitive pass per run (spec §10.5).
      CHECKIN_MAX_SENDS_PER_RUN = "100"
    }
  }

  tags = {
    Environment = var.environment
    Purpose     = "Companion check-in dispatcher scheduled worker"
  }
}

resource "aws_scheduler_schedule" "checkin_dispatcher_schedule" {
  name = "${var.environment}-${var.project_name}-checkin-dispatcher"

  flexible_time_window {
    mode = "OFF"
  }

  schedule_expression          = "rate(1 hour)"
  schedule_expression_timezone = "UTC"

  target {
    arn      = aws_lambda_function.checkin_dispatcher.arn
    role_arn = aws_iam_role.companion_scheduler_role.arn
  }
}

# ----------------------------------------------------------------------------
# prayer_reminder -- sends due prayer reminders (reminderCadence daily/weekly,
# nextReminderAt <= now), premium-gated, idempotent claim-before-send (§7, §15.2)
# ----------------------------------------------------------------------------
data "archive_file" "prayer_reminder_zip" {
  type        = "zip"
  source_dir  = "${path.module}/../../../lambdas/prayer_reminder"
  output_path = "${path.module}/../../../lambdas/prayer_reminder/prayer_reminder.zip"
  excludes    = ["__pycache__", "*.pyc", "*.zip", ".pytest_cache", "*.egg-info"]
}

resource "aws_lambda_function" "prayer_reminder" {
  function_name    = "${var.environment}-${var.project_name}-prayer-reminder"
  handler          = "prayer_reminder_handler.handler"
  runtime          = "python3.11"
  role             = aws_iam_role.lambda_exec_role.arn
  filename         = data.archive_file.prayer_reminder_zip.output_path
  source_code_hash = data.archive_file.prayer_reminder_zip.output_base64sha256
  # sms_layer supplies twilio for send_sms; langchain_layer supplies the vendored
  # shared modules (sms_notifications). Same minimal pair as the sibling workers —
  # we deliberately avoid the heavy shared_dependencies layer (250 MB limit).
  layers = [
    aws_lambda_layer_version.sms_layer.arn,
    aws_lambda_layer_version.langchain_layer.arn
  ]
  timeout     = 120
  memory_size = 512

  environment {
    variables = {
      ENVIRONMENT     = var.environment
      PROJECT_NAME    = var.project_name
      SECRET_ARN      = var.secret_arn
      USERS_TABLE     = local.users_table_name
      PRAYERS_TABLE   = aws_dynamodb_table.prayers.name
      VERSIFUL_PHONE  = var.versiful_phone
      POSTHOG_API_KEY = var.posthog_apikey
      # Fallback timezone for users without a stored tz when bucketing the 15-min run.
      DEFAULT_TIMEZONE = "America/New_York"
      # Local time-of-day reminders land (HH:MM in the user's timezone).
      PRAYER_REMINDER_TIME = "09:00"
      # Safety cap on sends per run, like CHECKIN_MAX_SENDS_PER_RUN.
      PRAYER_REMINDER_MAX_SENDS_PER_RUN = "100"
    }
  }

  tags = {
    Environment = var.environment
    Purpose     = "Companion prayer reminder scheduled worker"
  }
}

resource "aws_scheduler_schedule" "prayer_reminder_schedule" {
  name = "${var.environment}-${var.project_name}-prayer-reminder"

  flexible_time_window {
    mode = "OFF"
  }

  # Every 15 minutes — matches reading_plan_delivery / daily_verse_worker granularity.
  # Per-user local delivery windows are resolved inside the worker, so a 15-min cadence
  # lands each reminder within ~15 min of its target local time.
  schedule_expression          = "rate(15 minutes)"
  schedule_expression_timezone = "UTC"

  target {
    arn      = aws_lambda_function.prayer_reminder.arn
    role_arn = aws_iam_role.companion_scheduler_role.arn
  }
}
