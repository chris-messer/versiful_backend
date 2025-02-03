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

variable "domain_name" {
  description = "Domain name for the environment"
    }

variable "AWS_S3_IAM_SECRET" {
    description = "IAM secret for github action CI/CD setup"
    }