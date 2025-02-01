variable "environment" {
  description = "Deployment environment (e.g., dev, prod)"
  type        = string
  default     = "dev"
}


variable "secret_arn" {
  description = "ARN of the Secrets Manager secret"
  type        = string
}

