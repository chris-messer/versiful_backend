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