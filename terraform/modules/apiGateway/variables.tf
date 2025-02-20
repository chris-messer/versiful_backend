variable "environment" {
  description = "Deployment environment (e.g., dev, prod)"
  type        = string
  default     = "dev"
}

variable "region" {
  description = "Domain name for the environment"
}

variable "domain_name" {
  description = "Domain name for the environment"
}

variable "project_name" {
    description = "Name of the project"
    }

variable "acm_api_certificate_arn" {
    description = "Certificate arn"
    type        = string
    }

variable "api_acm_validation" {
    description = "Forces a depenency for DNS records to create before waiting for validation"
    }

variable "allowed_cors_origins" {
    description = "Allowed origins for CORS requests"
    }