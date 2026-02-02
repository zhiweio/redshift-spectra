# =============================================================================
# Secrets Manager Module - Terragrunt Configuration (LocalStack)
# =============================================================================
# This module creates Secrets Manager secrets in LocalStack for local development.
# Contains real test values for local testing.
# =============================================================================

# Include the LocalStack root terragrunt.hcl configuration
include "root" {
  path   = find_in_parent_folders("terragrunt-local.hcl")
  expose = true
}

# Include common variables
include "common" {
  path   = find_in_parent_folders("common.hcl")
  expose = true
}

# Load configuration
locals {
  account_vars = read_terragrunt_config(find_in_parent_folders("account.hcl"))
  region_vars  = read_terragrunt_config(find_in_parent_folders("region.hcl"))
  env_vars     = read_terragrunt_config(find_in_parent_folders("env.hcl"))

  account = local.account_vars.locals
  region  = local.region_vars.locals
  env     = local.env_vars.locals.settings
}

# Terraform module source
terraform {
  source = "${get_repo_root()}/terraform/modules/secrets-manager"
}

# Module inputs
inputs = {
  name_prefix = "${include.root.locals.project_name}-${include.root.locals.environment}"

  # Redshift credentials - real test values for LocalStack
  redshift_username = "admin"
  redshift_password = "LocalTest123!"

  # JWT secret - real test value for LocalStack (used in integration tests)
  jwt_secret = "local-jwt-secret-key-for-testing-only-123456"

  # No KMS in LocalStack
  kms_key_arn = null

  # Immediate deletion for local dev (0 = no waiting period)
  recovery_window_in_days = 0

  tags = include.root.locals.common_tags
}
