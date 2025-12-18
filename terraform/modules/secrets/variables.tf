variable "environment" {
  description = "Deployment environment (e.g., dev, prod)"
  type        = string
  default     = "dev"
}

variable "project_name" {
    description = "Name of the project"
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

# Test/e2e credentials (non-production)
variable "test_user_email" {
  description = "Test user email for e2e/authenticated tests"
  type        = string
  sensitive   = true
  default     = null
}

variable "test_user_password" {
  description = "Test user password for e2e/authenticated tests"
  type        = string
  sensitive   = true
  default     = null
}

variable "test_user_pool_client_id" {
  description = "Cognito User Pool Client ID for test user"
  type        = string
  sensitive   = true
  default     = null
}

variable "test_user_pool_client_secret" {
  description = "Cognito User Pool Client Secret for test user (if applicable)"
  type        = string
  sensitive   = true
  default     = null
}

variable "test_api_base_url" {
  description = "API base URL for tests (e.g., https://api.dev.versiful.io)"
  type        = string
  default     = null
}

variable "test_user_pool_id" {
  description = "Cognito User Pool ID for test user"
  type        = string
  sensitive   = true
  default     = null
}

variable "domain_name" {
  description = "Domain name for the environment"
    }

variable "AWS_S3_IAM_SECRET" {
    description = "IAM secret for github action CI/CD setup"
    }