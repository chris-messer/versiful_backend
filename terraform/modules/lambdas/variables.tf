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

variable "apiGateway_execution_arn" {
  description = "API Gateway execution ARN"
}

variable "secret_arn" {
  description = "ARN of the Secrets Manager secret"
  type        = string
}

variable "apiGateway_lambda_api_id" {
  description = "API Gateway Lambda API ID"
}