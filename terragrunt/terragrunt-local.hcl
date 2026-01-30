# =============================================================================
# Terragrunt Root Configuration - LocalStack
# =============================================================================
# This is the root terragrunt.hcl for LocalStack local development.
# It configures Terraform to use LocalStack endpoints instead of AWS.
#
# Usage:
#   Set TERRAGRUNT_CONFIG=terragrunt-local.hcl or use --terragrunt-config flag
#   Or use the provided scripts/localstack-deploy.sh helper script
# =============================================================================

# -----------------------------------------------------------------------------
# Local Variables
# -----------------------------------------------------------------------------
locals {
  # Parse the file path to get environment and region
  parsed = regex(".*/environments/(?P<env>\\w+)/(?P<region>[\\w-]+)/.*", get_terragrunt_dir())
  
  environment = local.parsed.env
  aws_region  = local.parsed.region
  
  # Load account-level variables
  account_vars = read_terragrunt_config(find_in_parent_folders("account.hcl"))
  
  # Load region-level variables
  region_vars = read_terragrunt_config(find_in_parent_folders("region.hcl", "region.hcl"), {
    locals = {}
  })
  
  # Load environment-level variables
  env_vars = read_terragrunt_config(find_in_parent_folders("env.hcl", "env.hcl"), {
    locals = {}
  })
  
  # Extract commonly used variables
  account_id   = local.account_vars.locals.account_id
  account_name = local.account_vars.locals.account_name
  
  # LocalStack configuration
  localstack_endpoint = try(local.region_vars.locals.localstack.endpoint, "http://localhost:4566")
  is_localstack       = try(local.env_vars.locals.is_localstack, false)
  
  # Project settings
  project_name = "redshift-spectra"
  
  # Common tags for all resources
  common_tags = {
    Project     = local.project_name
    Environment = local.environment
    ManagedBy   = "terragrunt"
    LocalStack  = "true"
  }
}

# -----------------------------------------------------------------------------
# Remote State Configuration (Local Backend for LocalStack)
# -----------------------------------------------------------------------------
# Use local backend instead of S3 for LocalStack development
# This avoids the chicken-and-egg problem of needing S3 to store state
remote_state {
  backend = "local"
  
  config = {
    path = "${get_terragrunt_dir()}/terraform.tfstate"
  }
  
  generate = {
    path      = "backend.tf"
    if_exists = "overwrite_terragrunt"
  }
}

# -----------------------------------------------------------------------------
# Provider Configuration for LocalStack
# -----------------------------------------------------------------------------
generate "provider" {
  path      = "provider.tf"
  if_exists = "overwrite_terragrunt"
  contents  = <<EOF
terraform {
  required_version = ">= 1.5.0"
  
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }
}

# LocalStack AWS Provider Configuration
# Uses tflocal-compatible endpoint configuration
provider "aws" {
  region                      = "${local.aws_region}"
  access_key                  = "test"
  secret_key                  = "test"
  skip_credentials_validation = true
  skip_metadata_api_check     = true
  skip_requesting_account_id  = true
  
  # LocalStack endpoints for all services
  endpoints {
    apigateway       = "${local.localstack_endpoint}"
    apigatewayv2     = "${local.localstack_endpoint}"
    cloudwatch       = "${local.localstack_endpoint}"
    cloudwatchlogs   = "${local.localstack_endpoint}"
    dynamodb         = "${local.localstack_endpoint}"
    iam              = "${local.localstack_endpoint}"
    lambda           = "${local.localstack_endpoint}"
    s3               = "${local.localstack_endpoint}"
    secretsmanager   = "${local.localstack_endpoint}"
    ssm              = "${local.localstack_endpoint}"
    sts              = "${local.localstack_endpoint}"
  }
  
  # S3 configuration for LocalStack
  s3_use_path_style = true
  
  default_tags {
    tags = ${jsonencode(local.common_tags)}
  }
}
EOF
}

# -----------------------------------------------------------------------------
# Common Inputs for All Modules
# -----------------------------------------------------------------------------
inputs = {
  project_name  = local.project_name
  environment   = local.environment
  aws_region    = local.aws_region
  is_localstack = true
  
  tags = local.common_tags
}

# -----------------------------------------------------------------------------
# Terraform Version Constraint
# -----------------------------------------------------------------------------
terraform_version_constraint = ">= 1.5.0"

# -----------------------------------------------------------------------------
# Terragrunt Version Constraint
# -----------------------------------------------------------------------------
terragrunt_version_constraint = ">= 0.50.0"
