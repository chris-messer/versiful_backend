locals {
  env_prefix  = var.environment
  domain      = "${local.env_prefix}.${var.domain_name}"         # prod.versiful.io, dev.versiful.io, etc.
  api_domain  = "api.${local.env_prefix}.${var.domain_name}"     # api.prod.versiful.io, etc.
  auth_domain = "auth.${local.env_prefix}.${var.domain_name}"    # auth.prod.versiful.io, etc.
}



data "aws_route53_zone" "zone" {
  name         = var.domain_name
  private_zone = false

}

# Route 53 Alias Record for CloudFront (Example)
resource "aws_route53_record" "cdn_alias" {
  zone_id = data.aws_route53_zone.zone.zone_id
  name    = local.domain
  type    = "A"  # Must be 'A' for an alias record
  alias {
    name                   = var.cdn_domain_name  # Target domain (CloudFront distribution, ELB, etc.)
    zone_id                = "Z2FDTNDATAQYW2"  # Hosted zone ID of the target service
    evaluate_target_health = false  # Usually false unless you want Route 53 to check health
  }
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
