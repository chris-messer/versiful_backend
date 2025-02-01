resource "aws_secretsmanager_secret" "versiful_secrets" {
  name = "${var.environment}-versiful_secrets"
}

resource "aws_secretsmanager_secret_version" "versiful_secret_version" {
  secret_id     = aws_secretsmanager_secret.versiful_secrets.id

  secret_string = jsonencode({
    "twilio_sid"          = var.twilio_sid,
    "twilio_secret"       = var.twilio_secret,
    "twilio_auth"         = var.twilio_auth,
    "twilio_account_sid"  = var.twilio_account_sid,
    "gpt"                 = var.gpt_api_key
  })
}