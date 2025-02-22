output "lambda_api_invoke_arn" {
  value = aws_apigatewayv2_api.lambda_api.api_endpoint
    }

output "apiGateway_target_domain_name" {
  value = aws_apigatewayv2_domain_name.api_domain.domain_name_configuration[0].target_domain_name
    }

output "apiGateway_hosted_zone_id" {
  value = aws_apigatewayv2_domain_name.api_domain.domain_name_configuration[0].hosted_zone_id
    }

output "apiGateway_execution_arn" {
  value = aws_apigatewayv2_api.lambda_api.execution_arn
    }

output "apiGateway_lambda_api_id" {
  value = aws_apigatewayv2_api.lambda_api.id
    }

output "jwt_auth_id" {
    value = aws_apigatewayv2_authorizer.jwt_auth.id
    }