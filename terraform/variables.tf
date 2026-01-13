variable "environment" {
  description = "environment (dev/staging/prod)"
  type        = string
}

variable "twilio_sid" {
  description = "Twilio SID"
  type        = string
  sensitive   = true
}

variable "twilio_secret" {
  description = "Twilio Secret"
  type        = string
  sensitive   = true
}

variable "twilio_auth" {
  description = "Twilio Auth Token"
  type        = string
  sensitive   = true
}

variable "twilio_account_sid" {
  description = "Twilio Account SID"
  type        = string
  sensitive   = true
}

variable "gpt_api_key" {
  description = "OpenAI GPT API Key"
  type        = string
  sensitive   = true
}

# Test/e2e credentials for automated tests
variable "test_user_email" {
  description = "Test user email for e2e tests"
  type        = string
  sensitive   = true
  default     = null
}

variable "test_user_password" {
  description = "Test user password for e2e tests"
  type        = string
  sensitive   = true
  default     = null
}

variable "test_user_pool_client_id" {
  description = "Cognito user pool client ID for tests"
  type        = string
  sensitive   = true
  default     = null
}

variable "test_user_pool_client_secret" {
  description = "Cognito user pool client secret for tests (if applicable)"
  type        = string
  sensitive   = true
  default     = null
}

variable "test_api_base_url" {
  description = "API base URL for tests"
  type        = string
  default     = null
}

variable "test_user_pool_id" {
  description = "Cognito user pool ID for tests"
  type        = string
  sensitive   = true
  default     = null
}

variable "google_client_id" {
  description = "Google client ID for cognito auth"
  type        = string
  sensitive   = true
}

variable "google_client_secret" {
  description = "Google client secret for cognito auth"
  type        = string
  sensitive   = true
}

variable "allowed_cors_origins" {
  description = "list of origins available for CORS requests"
  type        = list(string)
}

variable "stripe_publishable_key" {
  description = "Stripe publishable key (safe to expose in frontend)"
  type        = string
  sensitive   = true
}

variable "stripe_secret_key" {
  description = "Stripe secret key (backend only, never expose)"
  type        = string
  sensitive   = true
}

variable "versiful_phone" {
  description = "Versiful phone number in E.164 format (e.g., +18336811158)"
  type        = string
}

variable "posthog_apikey" {
  description = "PostHog API key for analytics"
  type        = string
  sensitive   = true
}

