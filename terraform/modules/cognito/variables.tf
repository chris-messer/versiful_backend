variable "environment" {
  description = "Deployment environment (e.g., dev, prod)"
  type        = string
  default     = "dev"
}

variable "user_pool_name" {
  description = "Name of the Cognito User Pool"
  type        = string
}

variable "user_pool_domain" {
  description = "Custom domain prefix for Cognito User Pool"
  type        = string
}

variable "domain_name" {
  description = "Domain name for the environment"
}

variable "region" {
  description = "Deployment region"
}

variable "project_name" {
    description = "Name of the project"
    }
