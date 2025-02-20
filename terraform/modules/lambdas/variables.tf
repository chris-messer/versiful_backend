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

variable "users_dynamodb_arn" {
    description = "ARN of the dynamodb table for users"
    }

variable "user_pool_client_id" {
    description = "Cognito client_id"
    }

variable "user_pool_id" {
    description = "Cognito USER_POOL_ID"
    }
