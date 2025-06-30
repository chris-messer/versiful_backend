locals {
  env_prefix  = var.environment
  domain      = "${local.env_prefix}.${var.domain_name}"         # prod.versiful.io, etc.
  api_domain  = "api.${local.env_prefix}.${var.domain_name}"     # api.prod.versiful.io, etc.
  auth_domain = "auth.${local.env_prefix}.${var.domain_name}"    # auth.prod.versiful.io, etc.
}

# 1. Create a Cognito User Pool
resource "aws_cognito_user_pool" "user_pool" {
  name = "${var.environment}-${var.project_name}-user-pool"

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

# 2. Create a Cognito User Pool Domain (custom domain is optional)
resource "aws_cognito_user_pool_domain" "aws_cognito_user_pool_domain" {
  domain       = local.auth_domain
  user_pool_id = aws_cognito_user_pool.user_pool.id
  certificate_arn = var.acm_cognito_certificate_arn
}


# TODO complete this step, and ensure it happens after the cognito userpool gets created
# Step 2a: Update the Route 53 Record After Cognito Domain Creation
# Replace the placeholder with the actual CloudFront distribution
resource "aws_route53_record" "cognito_custom_domain" {
  zone_id = var.aws_route53_zone_id
  name    = local.auth_domain         # e.g., dev.auth.versiful.io
  type    = "CNAME"
  ttl     = 300

  # Fetch the real CloudFront distribution associated with the Cognito domain
  records = [aws_cognito_user_pool_domain.aws_cognito_user_pool_domain.cloudfront_distribution]

  # Replace the placeholder
  depends_on = [aws_cognito_user_pool_domain.aws_cognito_user_pool_domain]
}


# 3. Add Google as an Identity Provider
resource "aws_cognito_identity_provider" "google" {
  user_pool_id  = aws_cognito_user_pool.user_pool.id
  provider_name = "Google" # Required to match Cognito's naming convention

  provider_type = "Google"

  provider_details = {
    client_id     = var.google_client_id       # Your Google OAuth Client ID
    client_secret = var.google_client_secret   # Your Google OAuth Client Secret
    authorize_scopes = "email profile openid"  # Scopes to request from Google
  }

  attribute_mapping = {
    email = "email"
    name  = "name"
  }
}

# 4. Create a Cognito User Pool Client
resource "aws_cognito_user_pool_client" "user_pool_client" {
  user_pool_id = aws_cognito_user_pool.user_pool.id
  name         = "${var.environment}-${var.project_name}-client"

  # Allow OAuth flows
  allowed_oauth_flows_user_pool_client = true
  allowed_oauth_flows = [
    "code",       # Authorization Code Flow
    "implicit"    # Optional, for frontend apps without a backend
  ]



  # Scopes for email, profile, and OpenID Connect
  allowed_oauth_scopes = [
    "email",
    "openid",
    "profile"
  ]

  # Support both Cognito's built-in auth and Google OAuth
  supported_identity_providers = [
    "COGNITO",  # For email/password login
    "Google"    # For Google OAuth
  ]

  # Redirect and logout URLs
  callback_urls = [
    "https://${local.domain}/callback",
    "http://localhost:5173/callback"
  ]

  logout_urls = [
    "https://${local.domain}/logout"
  ]

  # Explicit auth flows for email/password login
  explicit_auth_flows = [
    "ALLOW_USER_PASSWORD_AUTH",
    "ALLOW_REFRESH_TOKEN_AUTH",
    "ALLOW_CUSTOM_AUTH",
    "ALLOW_USER_SRP_AUTH",          # Enables Secure Remote Password (SRP) authentication
    "ALLOW_REFRESH_TOKEN_AUTH"
  ]
}
