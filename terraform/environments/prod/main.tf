terraform {
  required_version = ">= 1.3.0"
}

module "globals" {
  source        = "../../modules/globals"
    }

locals {
    environment     = var.environment
    region          = module.globals.region
    project_name    = module.globals.project_name
    domain     = module.globals.domain
    }


provider "aws" {
  region = local.region
}



module "secrets" {
  source = "../../modules/secrets"
  environment        = local.environment
  project_name       = local.project_name
  domain_name        = local.domain

  twilio_sid         = var.twilio_sid
  twilio_secret      = var.twilio_secret
  twilio_auth        = var.twilio_auth
  twilio_account_sid = var.twilio_account_sid
  gpt_api_key        = var.gpt_api_key
  AWS_S3_IAM_SECRET  = module.s3.AWS_S3_IAM_SECRET
}

module "s3" {
  source        = "../../modules/s3"
  domain_name   = local.domain
  project_name  = local.project_name
  environment   = local.environment
  cloudfront_cdn_arn = module.cloudFront.cloudfront_cdn_arn
    }

module "acm" {
    source          = "../../modules/acm"
    domain_name   = local.domain
    project_name  = local.project_name
    environment   = local.environment
    }

module apiGateway {
    source                  = "../../modules/apiGateway"
    acm_api_certificate_arn = module.acm.acm_api_certificate_arn
    api_acm_validation      = module.route53.api_acm_validation
    domain_name             = local.domain
    project_name            = local.project_name
    environment             = local.environment
    region                  = local.region
    allowed_cors_origins    = var.allowed_cors_origins
    authorizer_uri          = module.lambdas.authorizer_uri
    }

module "cloudFront" {
  source                 = "../../modules/cloudFront"
  acm_certificate_arn    = module.acm.acm_certificate_arn
  website_id             = module.s3.website_id
  website_endpoint       = module.s3.website_endpoint
  domain_name            = local.domain
  project_name           = local.project_name
  environment            = local.environment
  region                 = local.region
    }

module "route53" {
  source  = "../../modules/route53"
  cdn_domain_name                   = module.cloudFront.cdn_domain_name

  domain_validation_options         = module.acm.domain_validation_options
  api_domain_validation_options     = module.acm.api_domain_validation_options
  cognito_domain_validation_options = module.acm.cognito_domain_validation_options

  acm_api_certificate_arn           = module.acm.acm_api_certificate_arn
  acm_cognito_certificate_arn       = module.acm.acm_cognito_certificate_arn

#   cognito_user_pool_custom_domain   = module.cognito.cognito_user_pool_custom_domain

  apiGateway_target_domain_name     = module.apiGateway.apiGateway_target_domain_name
  apiGateway_hosted_zone_id         = module.apiGateway.apiGateway_hosted_zone_id

  domain_name                       = local.domain
  project_name                      = local.project_name
  environment                       = local.environment
  region                            = local.region
    }

module "lambdas" {
    source = "../../modules/lambdas"
    apiGateway_execution_arn    = module.apiGateway.apiGateway_execution_arn
    secret_arn                  = module.secrets.secret_arn
    apiGateway_lambda_api_id    = module.apiGateway.apiGateway_lambda_api_id
    users_dynamodb_arn          = module.dynamodb.users_dynamodb_arn
    domain_name                 = local.domain
    project_name                = local.project_name
    environment                 = local.environment
    region                      = local.region
    user_pool_id                = module.cognito.user_pool_id
    user_pool_client_id         = module.cognito.user_pool_client_id
    jwt_auth_id                 = module.apiGateway.jwt_auth_id
    }

module "cognito" {
  source                        = "../../modules/cognito"
  acm_cognito_certificate_arn   = module.acm.acm_cognito_certificate_arn
  domain_name                   = local.domain
  project_name                  = local.project_name
  environment                   = local.environment
  region                        = local.region
  aws_route53_zone_id           = module.route53.aws_route53_zone_id

  google_client_id = var.google_client_id
  google_client_secret = var.google_client_secret

}

module "dynamodb" {
  source                        = "../../modules/dynamodb"
  domain_name                   = local.domain
  project_name                  = local.project_name
  environment                   = local.environment
  region                        = local.region
  }