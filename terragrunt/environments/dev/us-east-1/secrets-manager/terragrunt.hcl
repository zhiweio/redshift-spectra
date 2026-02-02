# =============================================================================
# Secrets Manager Module - Terragrunt Configuration (Dev)
# =============================================================================
# This module creates Secrets Manager secrets for development environment.
# Uses placeholder values - replace with actual values via environment variables
# or CI/CD secrets injection.
# =============================================================================

# Include the root terragrunt.hcl configuration
include "root" {
  path   = find_in_parent_folders()
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

  # Redshift credentials - PLACEHOLDER VALUES
  # Replace via:
  #   - Environment variables: TF_VAR_redshift_username, TF_VAR_redshift_password
  #   - Or inject via CI/CD pipeline (GitHub Secrets, AWS SSM, etc.)
  redshift_username = get_env("TF_VAR_redshift_username", "PLACEHOLDER_REDSHIFT_USERNAME")
  redshift_password = get_env("TF_VAR_redshift_password", "PLACEHOLDER_REDSHIFT_PASSWORD")

  # JWT secret - PLACEHOLDER VALUE
  # Replace via:
  #   - Environment variable: TF_VAR_jwt_secret
  #   - Or inject via CI/CD pipeline
  # Recommended: Generate with: openssl rand -base64 32
  jwt_secret = get_env("TF_VAR_jwt_secret", "PLACEHOLDER_JWT_SECRET_REPLACE_ME_WITH_SECURE_VALUE")

  # Optional: Use KMS for encryption (recommended for production)
  kms_key_arn = null

  # 7-day recovery window for dev (allows secret recovery if accidentally deleted)
  recovery_window_in_days = 7

  tags = include.root.locals.common_tags
}
