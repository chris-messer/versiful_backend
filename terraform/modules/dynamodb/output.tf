output "users_dynamodb_arn" {
  value = aws_dynamodb_table.users.arn
}

output "sms_usage_dynamodb_arn" {
  value = aws_dynamodb_table.sms_usage.arn
}

output "promo_codes_dynamodb_arn" {
  value = aws_dynamodb_table.promo_codes.arn
}
