terraform {
  backend "s3" {
    bucket         = "versiful-state"
    key            = "shared/terraform.tfstate"
    region         = "us-east-1"
    dynamodb_table = "shared-versiful-terraform-locks"
    encrypt        = true
  }
}
