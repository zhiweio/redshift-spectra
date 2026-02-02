# =============================================================================
# S3 Module - Terragrunt Configuration
# =============================================================================
# This module creates S3 buckets for data storage and export results.
# =============================================================================

# Include the root terragrunt.hcl configuration
include "root" {
  path = find_in_parent_folders()
}

# Include common variables
include "common" {
  path   = find_in_parent_folders("common.hcl")
  expose = true
}

# Load environment-specific configuration
locals {
  env_vars     = read_terragrunt_config(find_in_parent_folders("env.hcl"))
  account_vars = read_terragrunt_config(find_in_parent_folders("account.hcl"))
  env          = local.env_vars.locals.settings
  account      = local.account_vars.locals

  common = include.common.locals
}

# Terraform module source
terraform {
  source = "${get_repo_root()}/terraform/modules/s3"
}

# Module inputs
inputs = {
  name_prefix = "${include.root.locals.project_name}-${include.root.locals.environment}"
  account_id  = local.account.account_id

  # Lifecycle configuration
  enable_lifecycle_rules     = lookup(local.env.s3, "lifecycle_enabled", local.common.s3_defaults.lifecycle_enabled)
  results_expiration_days    = lookup(local.env.s3, "results_expiration_days", local.common.s3_defaults.results_expiration_days)
  temp_files_expiration_days = lookup(local.env.s3, "temp_expiration_days", local.common.s3_defaults.temp_expiration_days)

  # Security settings
  enable_versioning = lookup(local.env.s3, "versioning_enabled", local.common.s3_defaults.versioning_enabled)
  kms_key_arn       = lookup(local.account.settings, "kms_key_arn", null)

  # CORS for presigned URLs
  enable_cors          = true
  cors_allowed_origins = lookup(local.env.cors, "allowed_origins", ["*"])
}
