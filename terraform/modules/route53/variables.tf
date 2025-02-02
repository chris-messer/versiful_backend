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

variable "cdn_domain_name" {
  description = "Cloudfront distribution domain name"
  type        = string
}

variable "domain_validation_options" {
  description = "ACM domain_validation_options"
    }

variable "api_domain_validation_options" {
  description = "ACM domain_validation_options"
    }

variable "apiGateway_target_domain_name" {
  description = "API Gateway target Domain Name"
}

variable "apiGateway_hosted_zone_id" {
  description = "API Gateway target hosted zone ID"
}