# resource "aws_route53_record" "cognito_cert_validation" {
#   for_each = {
#     for dvo in aws_acm_certificate.cognito_certificate.domain_validation_options : dvo.domain_name => {
#       name   = dvo.resource_record_name
#       type   = dvo.resource_record_type
#       value  = dvo.resource_record_value
#     }
#   }
#
#   zone_id = aws_route53_zone.versiful_zone.zone_id # Your Route53 hosted zone ID
#   name    = each.value.name
#   type    = each.value.type
#   records = [each.value.value]
#   ttl     = 300
# }
#
# resource "aws_acm_certificate_validation" "cognito_cert_validation" {
#   certificate_arn         = aws_acm_certificate.cognito_certificate.arn
#   validation_record_fqdns = [for record in aws_route53_record.cognito_cert_validation : record.fqdn]
# }