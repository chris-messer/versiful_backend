resource "aws_secretsmanager_secret" "secrets" {
  name = "${var.environment}-${var.project_name}_secrets"
}

resource "aws_secretsmanager_secret_version" "secret_version" {
  secret_id     = aws_secretsmanager_secret.secrets.id

  secret_string = jsonencode({
    "twilio_sid"          = var.twilio_sid,
    "twilio_secret"       = var.twilio_secret,
    "twilio_auth"         = var.twilio_auth,
    "twilio_account_sid"  = var.twilio_account_sid,
    "gpt"                 = var.gpt_api_key,
    "AWS_S3_IAM_SECRET"   = var.AWS_S3_IAM_SECRET,
    # Test/e2e credentials to support automated token fetch in tests
    "TEST_USER_EMAIL"         = var.test_user_email,
    "TEST_USER_PASSWORD"      = var.test_user_password,
    "USER_POOL_CLIENT_ID"     = var.test_user_pool_client_id,
    "USER_POOL_CLIENT_SECRET" = var.test_user_pool_client_secret,
    "API_BASE_URL"            = var.test_api_base_url,
    "USER_POOL_ID"            = var.test_user_pool_id
  })
}