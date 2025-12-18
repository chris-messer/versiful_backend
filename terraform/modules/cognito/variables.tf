variable "environment" {
  description = "Deployment environment (e.g., dev, prod)"
  type        = string
  default     = "dev"
}

variable "domain_name" {
  description = "Domain name for the environment"
}

variable "region" {
  description = "Domain name for the environment"
}

variable "project_name" {
    description = "Name of the project"
    }

variable "acm_cognito_certificate_arn" {
    description = "Cert ARN for auth domain"
    }

variable "google_client_id" {
  description = "Google OAuth Client ID"
  type        = string
}

variable "google_client_secret" {
  description = "Google OAuth Client Secret"
  type        = string
}

variable "aws_route53_zone_id" {
    description = "Route 53 Zone ID"
    }

variable "enable_ui_customization" {
  description = "Enable Cognito Hosted UI customization (requires domain present)"
  type        = bool
  default     = false
}