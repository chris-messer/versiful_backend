resource "aws_s3_bucket" "react_static_site" {
  bucket        = "${var.environment}-${var.project_name}-front-end" # Replace with a unique bucket name
  force_destroy = true
}

resource "aws_s3_bucket_website_configuration" "react_static_site_website" {
  bucket = aws_s3_bucket.react_static_site.id

  index_document {
    suffix = "index.html"
  }

  error_document {
    key = "index.html"
  }
}

resource "aws_s3_bucket_public_access_block" "react_static_site_public_access" {
  bucket = aws_s3_bucket.react_static_site.id

  block_public_acls       = false
  block_public_policy     = false
  ignore_public_acls      = false
  restrict_public_buckets = false
}

resource "aws_s3_bucket_policy" "react_static_site_policy" {
  bucket = aws_s3_bucket.react_static_site.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "PublicReadGetObject"
        Effect    = "Allow"
        Principal = "*"
        Action    = "s3:GetObject"
        Resource  = "${aws_s3_bucket.react_static_site.arn}/*"
      }
    ]
  })
}

# Format phone number for display
locals {
  # Extract digits from +18336811158 to get area(833), prefix(681), line(1158)
  phone_digits = replace(var.versiful_phone, "+1", "")
  phone_area   = substr(local.phone_digits, 0, 3)
  phone_prefix = substr(local.phone_digits, 3, 3)
  phone_line   = substr(local.phone_digits, 6, 4)
  
  # Format: (833) 681-1158
  phone_display = "(${local.phone_area}) ${local.phone_prefix}-${local.phone_line}"
  
  # Format: 833-681-1158
  phone_sms = "${local.phone_area}-${local.phone_prefix}-${local.phone_line}"
}

# Generate config.json with environment-specific values
resource "local_file" "config_json" {
  filename = "${path.module}/config.json"
  
  content = jsonencode({
    environment = var.environment
    phone = {
      e164    = var.versiful_phone
      display = local.phone_display
      sms     = local.phone_sms
    }
  })
}

# Upload config.json to S3
resource "aws_s3_object" "config_json" {
  bucket        = aws_s3_bucket.react_static_site.id
  key           = "config.json"
  content       = local_file.config_json.content
  content_type  = "application/json"
  cache_control = "public, max-age=300"  # Cache for 5 minutes
  etag          = md5(local_file.config_json.content)
  
  depends_on = [
    aws_s3_bucket_policy.react_static_site_policy
  ]
}

resource "null_resource" "deploy_react_project" {
  provisioner "local-exec" {
    command = <<EOT
      rm -rf versiful_frontend &&
      git clone --branch ${var.environment == "prod" ? "main" : var.environment} https://github.com/chris-messer/versiful_frontend.git versiful_frontend &&
      https://github.com/chris-messer/versiful_frontend.git
      cd versiful_frontend &&
      npm install &&
      npm run build &&
      cd .. &&
      aws s3 sync versiful_frontend/dist s3://${aws_s3_bucket.react_static_site.bucket} --delete
      aws s3 sync versiful_frontend/dist s3://${aws_s3_bucket.react_static_site.bucket} --delete --exact-timestamps --metadata-directive REPLACE
      aws s3 cp versiful_frontend/dist/index.html s3://${var.environment}-${var.project_name}-front-end/index.html --content-type "text/html"

    EOT
  }
#   triggers = {
#     force_redeploy = timestamp()
#   }

}

# Github Actions CI/CD setup
# IAM User for GitHub Actions
resource "aws_iam_user" "github_actions_user" {
  name = "${var.environment}-${var.project_name}-github-actions-deploy"
}

# IAM Access Key for GitHub Actions
resource "aws_iam_access_key" "github_access_key" {
  user = aws_iam_user.github_actions_user.name
}

# IAM Policy for S3 Upload
resource "aws_iam_policy" "s3_deploy_policy" {
  name        = "${var.environment}-${var.project_name}-S3DeployPolicy"
  description = "Policy to allow GitHub Actions to deploy files to S3"
  policy      = <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["s3:PutObject", "s3:DeleteObject", "s3:ListBucket"],
      "Resource": [
        "arn:aws:s3:::${aws_s3_bucket.react_static_site.id}",
        "arn:aws:s3:::${aws_s3_bucket.react_static_site.id}/*"
      ]
    },
    {
      "Effect": "Allow",
      "Action": "cloudfront:CreateInvalidation",
      "Resource": "${var.cloudfront_cdn_arn}"
    }
  ]
}
EOF
}

# Attach Policy to IAM User
resource "aws_iam_user_policy_attachment" "attach_s3_policy" {
  user       = aws_iam_user.github_actions_user.name
  policy_arn = aws_iam_policy.s3_deploy_policy.arn
}