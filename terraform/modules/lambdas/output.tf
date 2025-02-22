output "authorizer_uri" {
    value = aws_lambda_function.jwt_authorizer.invoke_arn
    }