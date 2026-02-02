# =============================================================================
# Terragrunt Root Configuration
# =============================================================================
# This is the root terragrunt.hcl that all child configurations inherit from.
# It defines common settings like remote state, provider configuration, and
# shared inputs that apply to all environments.
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

  # Project settings
  project_name = "redshift-spectra"

  # Common tags for all resources
  common_tags = {
    Project     = local.project_name
    Environment = local.environment
    ManagedBy   = "terragrunt"
    Repository  = "https://github.com/zhiweio/redshift-spectra"
  }
}

# -----------------------------------------------------------------------------
# Remote State Configuration (S3 + DynamoDB)
# -----------------------------------------------------------------------------
remote_state {
  backend = "s3"

  config = {
    encrypt        = true
    bucket         = "${local.project_name}-terraform-state-${local.account_id}"
    key            = "${path_relative_to_include()}/terraform.tfstate"
    region         = local.aws_region
    dynamodb_table = "${local.project_name}-terraform-locks"

    # Enable server-side encryption
    s3_bucket_tags      = local.common_tags
    dynamodb_table_tags = local.common_tags
  }

  generate = {
    path      = "backend.tf"
    if_exists = "overwrite_terragrunt"
  }
}

# -----------------------------------------------------------------------------
# Provider Configuration
# -----------------------------------------------------------------------------
generate "provider" {
  path      = "provider.tf"
  if_exists = "overwrite_terragrunt"
  contents  = <<EOF
terraform {
  required_version = ">= 1.14.0"

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

provider "aws" {
  region = "${local.aws_region}"

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
  project_name = local.project_name
  environment  = local.environment
  aws_region   = local.aws_region

  tags = local.common_tags
}

# -----------------------------------------------------------------------------
# Terraform Version Constraint
# -----------------------------------------------------------------------------
terraform_version_constraint = ">= 1.14.0"

# -----------------------------------------------------------------------------
# Terragrunt Version Constraint
# -----------------------------------------------------------------------------
terragrunt_version_constraint = ">= 0.99.0"
