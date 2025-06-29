terraform {
  backend "s3" {
    bucket         = "versiful-state"
    key            = "prod/terraform.tfstate"
    region         = "us-east-1"
    dynamodb_table = "prod-versiful-terraform-locks"
    encrypt        = true
  }
}
