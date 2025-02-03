output "api_acm_validation" {
    value = aws_route53_record.acm_api_validation
    }

output "aws_route53_zone_id" {
    value = data.aws_route53_zone.zone.zone_id
    }