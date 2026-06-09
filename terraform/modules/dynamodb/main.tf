resource "aws_dynamodb_table" "users" {
  name         = "${var.environment}-${var.project_name}-users"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "userId"

  attribute {
    name = "userId"
    type = "S"
  }

  # phoneNumber attribute + GSI so the unregistered-SMS lookup becomes a Query
  # instead of a Scan (COMPANION_SPEC.md §5.1 -- fixes the Scan + Limit-before-filter
  # correctness bug). Spec does not name the index, so use phoneNumber-index.
  attribute {
    name = "phoneNumber"
    type = "S"
  }

  global_secondary_index {
    name            = "phoneNumber-index"
    hash_key        = "phoneNumber"
    projection_type = "ALL"
  }
}

# Promo code tracking for Stripe coupons/promotions
resource "aws_dynamodb_table" "promo_codes" {
  name         = "${var.environment}-${var.project_name}-promo-codes"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "code"

  attribute {
    name = "code"
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