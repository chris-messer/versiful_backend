locals {
  domain = var.environment == "prod" ? "www.${var.domain_name}" : "${var.environment}.${var.domain_name}"
  api_domain = var.environment == "prod" ? "api.${var.domain_name}" : "${var.environment}.api.${var.domain_name}"
}


data "aws_route53_zone" "versiful" {
  name         = "versiful.io"
  private_zone = false

}

# Route 53 CNAME Record
resource "aws_route53_record" "cdn_cname" {
  zone_id = data.aws_route53_zone.versiful.zone_id
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

  zone_id = data.aws_route53_zone.versiful.zone_id
  name    = each.value.name
  type    = each.value.type
  records = [each.value.value]
  ttl     = 300
}

resource "aws_route53_record" "acm_api_validation" {
  for_each = {
    for dvo in var.api_domain_validation_options : dvo.domain_name => {
      name  = dvo.resource_record_name
      type  = dvo.resource_record_type
      value = dvo.resource_record_value
    }
  }

  zone_id = data.aws_route53_zone.versiful.zone_id
  name    = each.value.name
  type    = each.value.type
  records = [each.value.value]
  ttl     = 300
}


# Route 53 Configuration for Custom Domain
resource "aws_route53_record" "api_dns" {
  zone_id = data.aws_route53_zone.versiful.zone_id
  name    = local.api_domain
  type    = "A"

  alias {
    name                   = var.apiGateway_target_domain_name
    zone_id                = var.apiGateway_hosted_zone_id
    evaluate_target_health = false
  }
}