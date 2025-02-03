output "website_id" {
  value = aws_s3_bucket.react_static_site.id
}

output "website_endpoint" {
  value = aws_s3_bucket_website_configuration.react_static_site_website.website_endpoint
}

output "s3_bucket_id" {
    value = aws_s3_bucket.react_static_site.id
    }

output "aws_access_key_id" {
  value     = aws_iam_access_key.github_access_key.id
  sensitive = true
}

output "AWS_S3_IAM_SECRET" {
  value     = aws_iam_access_key.github_access_key.secret
  sensitive = true
}

output "s3_bucket_name" {
  value = aws_s3_bucket.react_static_site.id
}