resource "aws_acm_certificate" "cognito_cert" {
  domain_name       = local.auth_domain
  validation_method = "DNS"

  tags = {
    Name = "Cognito Custom Domain Certificate"
  }

    lifecycle {
    create_before_destroy = true
  }
}
