# =============================================================================
# S3 Module - Terragrunt Configuration (LocalStack)
# =============================================================================
# This module creates S3 buckets in LocalStack for local development.
# =============================================================================

# Include the LocalStack root terragrunt.hcl configuration
include "root" {
  path = find_in_parent_folders("terragrunt-local.hcl")
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
  
  # Allow force destroy for local development (easy cleanup)
  force_destroy = true
  
  # Disable versioning for LocalStack (simpler)
  enable_versioning = false
  
  # Lifecycle configuration (shorter for local dev)
  enable_lifecycle_rules      = true
  results_expiration_days     = 1
  bulk_export_expiration_days = 1
  bulk_import_expiration_days = 1
  temp_files_expiration_days  = 1
  
  # No intelligent tiering in LocalStack
  enable_intelligent_tiering = false
  
  # No KMS in LocalStack
  kms_key_arn = null
  
  # CORS for presigned URLs
  enable_cors          = true
  cors_allowed_origins = ["*"]
  
  # Disable bucket policy in LocalStack (permissive by default)
  enable_bucket_policy = false
  
  # No access logging in LocalStack
  enable_access_logging = false
}
