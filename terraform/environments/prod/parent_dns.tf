

# ACM certificate covering versiful.io + www.versiful.io
resource "aws_acm_certificate" "root_domains_cert" {
  provider          = aws.us-east-1
  domain_name       = local.domain             # versiful.io
  validation_method = "DNS"

  subject_alternative_names = [
    "www.${local.domain}",                     # www.versiful.io
  ]

  tags = {
    Name = "Root domains certificate for versiful.io"
  }

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_route53_record" "root_cert_validation" {
  for_each = {
    for dvo in aws_acm_certificate.root_domains_cert.domain_validation_options : dvo.domain_name => {
      name   = dvo.resource_record_name
      type   = dvo.resource_record_type
      value  = dvo.resource_record_value
    }
  }

  zone_id = module.route53.aws_route53_zone_id
  name    = each.value.name
  type    = each.value.type
  records = [each.value.value]
  ttl     = 300
}

resource "aws_acm_certificate_validation" "root_cert_validation" {
  provider                = aws.us-east-1
  certificate_arn         = aws_acm_certificate.root_domains_cert.arn
  validation_record_fqdns = [for record in aws_route53_record.root_cert_validation : record.fqdn]
}

# DNS records pointing versiful.io + www.versiful.io to your existing prod CloudFront distribution
resource "aws_route53_record" "versiful_root" {
  zone_id = module.route53.aws_route53_zone_id
  name    = local.domain  # versiful.io
  type    = "A"

  alias {
    name                   = module.cloudFront.cdn_domain_name  # existing prod.versiful.io CloudFront
    zone_id                = "Z2FDTNDATAQYW2"                   # CloudFront's hosted zone ID
    evaluate_target_health = false
  }
}

resource "aws_route53_record" "versiful_www" {
  zone_id = module.route53.aws_route53_zone_id
  name    = "www.${local.domain}"  # www.versiful.io
  type    = "A"

  alias {
    name                   = module.cloudFront.cdn_domain_name  # existing prod.versiful.io CloudFront
    zone_id                = "Z2FDTNDATAQYW2"                   # CloudFront's hosted zone ID
    evaluate_target_health = false
  }
}

# Optional: wait for the new cert to be issued
resource "null_resource" "wait_for_acm_validation" {
  depends_on = [aws_acm_certificate_validation.root_cert_validation]

  provisioner "local-exec" {
    command = <<EOT
      CERT_ARN="${aws_acm_certificate.root_domains_cert.arn}"
      while true; do
        STATUS=$(aws acm describe-certificate --certificate-arn $CERT_ARN --region ${local.region} --query "Certificate.Status" --output text)
        echo "ACM Certificate Status: $STATUS"
        if [ "$STATUS" == "ISSUED" ]; then
          echo "Certificate validated!"
          break
        fi
        echo "Waiting for ACM validation..."
        sleep 10
      done
    EOT
  }

  triggers = {
    cert_arn = aws_acm_certificate.root_domains_cert.arn
  }
}
