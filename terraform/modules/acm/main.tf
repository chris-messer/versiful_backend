locals {
  env_prefix  = var.environment
  domain      = "${local.env_prefix}.${var.domain_name}"
  api_domain  = "api.${local.env_prefix}.${var.domain_name}"
  auth_domain = "auth.${local.env_prefix}.${var.domain_name}"

  subject_alternative_names = var.environment == "prod" ? [
    var.domain_name,         # versiful.io
    "www.${var.domain_name}" # www.versiful.io
  ] : []
}


# Create an ACM Certificate in us-east-1 for the primary domain
resource "aws_acm_certificate" "cert" {
  domain_name       = local.domain
  validation_method = "DNS"
  subject_alternative_names = local.subject_alternative_names
  lifecycle {
    create_before_destroy = true
  }
}