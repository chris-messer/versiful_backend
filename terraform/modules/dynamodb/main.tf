resource "aws_dynamodb_table" "users" {
  name         = "${var.environment}-${var.project_name}-users"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "userId"

  attribute {
    name = "userId"
    type = "S"
  }
}

# Phone-level SMS usage tracking (per environment)
resource "aws_dynamodb_table" "sms_usage" {
  name         = "${var.environment}-${var.project_name}-sms-usage"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "phoneNumber"

  attribute {
    name = "phoneNumber"
    type = "S"
  }
}