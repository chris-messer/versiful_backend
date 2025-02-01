terraform {
  required_version = ">= 1.3.0"
}


provider "aws" {
  region = "us-east-1"
}

resource "null_resource" "debug_path_root" {
  provisioner "local-exec" {
    command = "echo path.module=${path.module}"
  }
}

module "secrets" {
  source = "../../modules/secrets"
  twilio_sid         = var.twilio_sid
  twilio_secret      = var.twilio_secret
  twilio_auth        = var.twilio_auth
  twilio_account_sid = var.twilio_account_sid
  gpt_api_key        = var.gpt_api_key
  domain_name        = var.domain_name
}

# module "other" {
#     source = "../../modules/other"
#     secret_arn = module.secrets.secret_arn
#     }

module "s3" {
  source        = "../../modules/s3"
  domain_name   = var.domain_name
    }

module "acm" {
    source          = "../../modules/acm"
    domain_name     = var.domain_name
    }

module apiGateway {
    source                  = "../../modules/apiGateway"
    acm_api_certificate_arn = module.acm.acm_api_certificate_arn
    api_acm_validation      = module.route53.api_acm_validation
    domain_name             = var.domain_name
    }

module "cloudFront" {
  source                 = "../../modules/cloudFront"
  acm_certificate_arn    = module.acm.acm_certificate_arn
  website_id             = module.s3.website_id
  website_endpoint       = module.s3.website_endpoint
  domain_name            = var.domain_name
    }

module "route53" {
  source  = "../../modules/route53"
  cdn_domain_name                   = module.cloudFront.cdn_domain_name
  domain_validation_options         = module.acm.domain_validation_options
  api_domain_validation_options     = module.acm.api_domain_validation_options
  apiGateway_target_domain_name     = module.apiGateway.apiGateway_target_domain_name
  apiGateway_hosted_zone_id         = module.apiGateway.apiGateway_hosted_zone_id
  domain_name                       = var.domain_name
    }

module "lambdas" {
    source = "../../modules/lambdas"
    apiGateway_execution_arn    = module.apiGateway.apiGateway_execution_arn
    secret_arn                  = module.secrets.secret_arn
    apiGateway_lambda_api_id    = module.apiGateway.apiGateway_lambda_api_id
    domain_name        = var.domain_name
    }
