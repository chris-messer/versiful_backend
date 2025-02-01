output "website_id" {
  value = aws_s3_bucket.react_static_site.id
}

output "website_endpoint" {
  value = aws_s3_bucket_website_configuration.react_static_site_website.website_endpoint
}