resource "aws_cognito_user_pool" "user_pool" {
  name = var.user_pool_name

  # Allow users to sign in with email
  username_attributes = ["email"]

  # Password policy
  password_policy {
    minimum_length    = 8
    require_lowercase = false
    require_numbers   = false
    require_symbols   = false
    require_uppercase = false
  }

  # MFA settings (optional)
  mfa_configuration = "OFF"
}

resource "aws_cognito_user_pool_client" "user_pool_client" {
  name         = "${var.user_pool_name}-client"
  user_pool_id = aws_cognito_user_pool.user_pool.id

  # Allow username and password login
  explicit_auth_flows = [
    "ALLOW_USER_PASSWORD_AUTH",
    "ALLOW_REFRESH_TOKEN_AUTH",
  ]

  # Prevent client secret for browser-based apps
  generate_secret = false
}

resource "aws_cognito_user_pool_domain" "user_pool_domain" {
  domain       = var.user_pool_domain
  user_pool_id = aws_cognito_user_pool.user_pool.id
}
