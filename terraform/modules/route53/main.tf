locals {
  domain = var.environment == "prod" ? "www.${var.domain_name}" : "${var.environment}.${var.domain_name}"
  api_domain = var.environment == "prod" ? "api.${var.domain_name}" : "${var.environment}.api.${var.domain_name}"
}


data "aws_route53_zone" "zone" {
  name         = var.domain_name
  private_zone = false

}

# Route 53 CNAME Record
resource "aws_route53_record" "cdn_cname" {
  zone_id = data.aws_route53_zone.zone.zone_id
  name    = local.domain
  type    = "CNAME"
  ttl     = 300
  records = [var.cdn_domain_name]
}

# Add DNS records for cert validation
resource "aws_route53_record" "acm_validation" {
  for_each = {
    for dvo in var.domain_validation_options : dvo.domain_name => {
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
