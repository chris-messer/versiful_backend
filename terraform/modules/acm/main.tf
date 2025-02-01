locals {
  domain = var.environment == "prod" ? "www.${var.domain_name}" : "${var.environment}.${var.domain_name}"
  api_domain = var.environment == "prod" ? "api.${var.domain_name}" : "${var.environment}.api.${var.domain_name}"
}

# Create an ACM Certificate in us-east-1 for the primary domain
resource "aws_acm_certificate" "cert" {
  domain_name       = local.domain
  validation_method = "DNS"

  lifecycle {
    create_before_destroy = true
  }
}

# Request an ACM Certificate (Unique for Each Environment)
resource "aws_acm_certificate" "api_cert" {
  domain_name       = local.api_domain
  validation_method = "DNS"

  lifecycle {
    create_before_destroy = true
  }
}