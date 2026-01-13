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
    posthog = {
      apiKey = var.posthog_apikey
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

# Generate vCard with environment-specific phone number
locals {
  vcard_content = <<-VCARD
BEGIN:VCARD
VERSION:3.0
N:;Versiful;;;
FN:Versiful
ORG:Versiful
TEL;TYPE=CELL:${var.versiful_phone}
URL:https://versiful.io
PHOTO;ENCODING=b;TYPE=PNG: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
NOTE:Biblical guidance and wisdom via text message
END:VCARD
VCARD
}

# Generate vCard file locally
resource "local_file" "vcard" {
  filename = "${path.module}/versiful-contact.vcf"
  content  = local.vcard_content
}

# Upload vCard to S3
resource "aws_s3_object" "vcard" {
  bucket        = aws_s3_bucket.react_static_site.id
  key           = "versiful-contact.vcf"
  content       = local_file.vcard.content
  content_type  = "text/vcard"
  cache_control = "public, max-age=86400"  # Cache for 24 hours
  etag          = md5(local_file.vcard.content)
  
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