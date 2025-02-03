# Output ACM ARN to Use in CloudFront
output "acm_certificate_arn" {
  value = aws_acm_certificate.cert.arn
}

output "acm_api_certificate_arn" {
  value = aws_acm_certificate.api_cert.arn
}

output "acm_cognito_certificate_arn" {
  value = aws_acm_certificate.cognito_cert.arn
}

output "domain_validation_options" {
  value = aws_acm_certificate.cert.domain_validation_options
}

output "api_domain_validation_options" {
  value = aws_acm_certificate.api_cert.domain_validation_options
}

output "cognito_domain_validation_options" {
  value = aws_acm_certificate.cognito_cert.domain_validation_options
}