variable "environment" {
  description = "Deployment environment (e.g., dev, prod)"
  type        = string
  default     = "dev"
}

variable "project_name" {
    description = "Name of the project"
    }

variable "domain_name" {
  description = "Domain name for the environment"
}

variable "cloudfront_cdn_arn" {
    description = "ARN of the main CF distro, to pass for IAM access for invalidating cache"
    }

variable "versiful_phone" {
  description = "Versiful phone number in E.164 format"
  type        = string
}