resource "aws_route53_record" "acm_api_validation" {
  for_each = {
    for dvo in var.api_domain_validation_options : dvo.domain_name => {
      name  = dvo.resource_record_name
      type  = dvo.resource_record_type
      value = dvo.resource_record_value
    }
  }

  zone_id = data.aws_route53_zone.zone.zone_id
  name    = each.value.name
  type    = each.value.type
  records = [each.value.value]
  ttl     = 300
}

# Route 53 Configuration for Custom Domain
resource "aws_route53_record" "api_dns" {
  zone_id = data.aws_route53_zone.zone.zone_id
  name    = local.api_domain
  type    = "A"

  alias {
    name                   = var.apiGateway_target_domain_name
    zone_id                = var.apiGateway_hosted_zone_id
    evaluate_target_health = false
  }
}

# # Wait for validations
# resource "aws_acm_certificate_validation" "api_cert_validation" {
#   certificate_arn         = var.acm_api_certificate_arn
#   validation_record_fqdns = [for record in aws_route53_record.cognito_cert_validation : record.fqdn]
# }