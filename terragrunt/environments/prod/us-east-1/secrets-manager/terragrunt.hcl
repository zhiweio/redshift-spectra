# =============================================================================
# Secrets Manager Module - Terragrunt Configuration (Prod)
# =============================================================================
# This module creates Secrets Manager secrets for production environment.
# Uses placeholder values - MUST be replaced with actual values via:
#   - Environment variables (TF_VAR_*)
#   - CI/CD secrets injection
#   - AWS SSM Parameter Store
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

  # Redshift credentials - PLACEHOLDER VALUES (MUST BE REPLACED FOR PRODUCTION)
  # Replace via:
  #   - Environment variables: TF_VAR_redshift_username, TF_VAR_redshift_password
  #   - CI/CD pipeline secrets (GitHub Secrets, AWS SSM, HashiCorp Vault, etc.)
  #
  # SECURITY WARNING: Never commit real credentials to version control!
  redshift_username = get_env("TF_VAR_redshift_username", "PLACEHOLDER_REDSHIFT_USERNAME")
  redshift_password = get_env("TF_VAR_redshift_password", "PLACEHOLDER_REDSHIFT_PASSWORD")

  # JWT secret - PLACEHOLDER VALUE (MUST BE REPLACED FOR PRODUCTION)
  # Replace via:
  #   - Environment variable: TF_VAR_jwt_secret
  #   - CI/CD pipeline secrets
  #
  # Generate secure secret with: openssl rand -base64 64
  # Recommended: At least 256 bits (32+ bytes) of entropy
  jwt_secret = get_env("TF_VAR_jwt_secret", "PLACEHOLDER_JWT_SECRET_REPLACE_ME_WITH_SECURE_VALUE")

  # Optional: Use customer-managed KMS key for encryption (recommended for production)
  # Create KMS key separately and reference here
  kms_key_arn = null

  # 30-day recovery window for production (protects against accidental deletion)
  recovery_window_in_days = 30

  tags = include.root.locals.common_tags
}
