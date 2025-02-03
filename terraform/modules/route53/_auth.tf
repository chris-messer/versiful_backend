resource "aws_route53_record" "cognito_cert_validation" {
  for_each = {
    for dvo in var.cognito_domain_validation_options : dvo.domain_name => {
      name   = dvo.resource_record_name
      type   = dvo.resource_record_type
      value  = dvo.resource_record_value
    }
  }

  zone_id = data.aws_route53_zone.zone.zone_id
  name    = each.value.name
  type    = each.value.type
  records = [each.value.value]
  ttl     = 300
}

#TODO move to shared resources
resource "aws_route53_record" "cognito_parent_placeholder" {
  zone_id = data.aws_route53_zone.zone.zone_id
  name    = "auth.${var.domain_name}"
  type    = "A"
  ttl     = 300
  records = ["192.0.2.1"] # Placeholder value
}


resource "aws_route53_record" "cognito_placeholder" {
  zone_id = data.aws_route53_zone.zone.zone_id
  name    = local.auth_domain # e.g., dev.auth.versiful.io
  type    = "A"
  ttl     = 300
  records = ["192.0.2.1"] # Placeholder value
}

# Wait for validations
resource "aws_acm_certificate_validation" "cognito_cert_validation" {
  certificate_arn         = var.acm_cognito_certificate_arn
  validation_record_fqdns = [for record in aws_route53_record.cognito_cert_validation : record.fqdn]
}