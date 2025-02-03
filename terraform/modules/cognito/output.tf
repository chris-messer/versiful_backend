output "user_pool_id" {
  description = "ID of the Cognito User Pool"
  value       = aws_cognito_user_pool.user_pool.id
}
#
# output "user_pool_client_id" {
#   description = "ID of the Cognito User Pool Client"
#   value       = aws_cognito_user_pool_client.user_pool_client.id
# }
#
# output "custom_domain" {
#   value = aws_cognito_user_pool_domain.custom_domain.domain
# }

# output "cognito_user_pool_custom_domain" {
#     value = aws_cognito_user_pool_domain.custom_domain.cloudfront_distribution
#     }