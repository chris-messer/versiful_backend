locals {
  domain = var.environment == "prod" ? "www.${var.domain_name}" : "${var.environment}.${var.domain_name}"
}

# Delay cloudfront distrobution until certificate is validated
resource "null_resource" "wait_for_acm_validation" {
  provisioner "local-exec" {
    command = <<EOT
      CERT_ARN="${var.acm_certificate_arn}"
      while true; do
        STATUS=$(aws acm describe-certificate --certificate-arn $CERT_ARN --region us-east-1 --query "Certificate.Status" --output text)
        echo "ACM Certificate Status: $STATUS"
        if [ "$STATUS" == "ISSUED" ]; then
          echo "Certificate validated!"
          break
        fi
        echo "Waiting for ACM validation..."
        sleep 10
      done
    EOT
  }

  triggers = {
    cert_arn = var.acm_certificate_arn
  }
}



# CloudFront Distribution
resource "aws_cloudfront_distribution" "cdn" {
  origin {
    domain_name = var.website_endpoint
    origin_id   = "S3-Static-Website"

    custom_origin_config {
      http_port              = 80
      https_port             = 443
      origin_protocol_policy = "http-only"
      origin_ssl_protocols   = ["TLSv1.2"]
    }
  }

  enabled             = true
  default_root_object = "index.html"

  aliases = [local.domain]


  viewer_certificate {
    acm_certificate_arn      = var.acm_certificate_arn
    ssl_support_method       = "sni-only"
    minimum_protocol_version = "TLSv1.2_2021"
  }

  default_cache_behavior {
    allowed_methods  = ["GET", "HEAD", "OPTIONS"]
    cached_methods   = ["GET", "HEAD"]
    target_origin_id = "S3-Static-Website"

    forwarded_values {
      query_string = false
      cookies {
        forward = "none"
      }
    }

    viewer_protocol_policy = "redirect-to-https"
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }
  depends_on = [null_resource.wait_for_acm_validation]
}

# Invalidate the cloud formation cache after deployment
resource "null_resource" "cloudfront_invalidation" {
  depends_on = [aws_cloudfront_distribution.cdn]  # ✅ Ensures CloudFront deploys first

  provisioner "local-exec" {
    command = <<EOT
      DISTRIBUTION_ID="${aws_cloudfront_distribution.cdn.id}"
      aws cloudfront create-invalidation --distribution-id $DISTRIBUTION_ID --paths "/*"
    EOT
  }

  triggers = {
    always_run = timestamp()  # ✅ Forces invalidation on every Terraform apply
  }
}
