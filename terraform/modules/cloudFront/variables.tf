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

variable "website_id" {
  description = "S3 website ID"
  type        = string
}

variable "website_endpoint" {
  description = "S3 website endpoint"
  type        = string
}

variable "acm_certificate_arn" {
    description = "Certificate arn"
    type        = string
    }