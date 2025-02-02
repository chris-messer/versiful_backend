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
