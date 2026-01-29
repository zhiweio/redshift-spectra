# =============================================================================
# S3 Module - Production
# =============================================================================

include "root" {
  path = find_in_parent_folders()
}

include "common" {
  path   = find_in_parent_folders("common.hcl")
  expose = true
}

locals {
  env_vars     = read_terragrunt_config(find_in_parent_folders("env.hcl"))
  account_vars = read_terragrunt_config(find_in_parent_folders("account.hcl"))
  env          = local.env_vars.locals.settings
  account      = local.account_vars.locals
  common       = include.common.locals
}

terraform {
  source = "${get_repo_root()}/terraform/modules/s3"
}

inputs = {
  name_prefix = "${include.root.locals.project_name}-${include.root.locals.environment}"
  account_id  = local.account.account_id
  
  enable_lifecycle_rules     = true
  results_expiration_days    = lookup(local.env.s3, "results_expiration_days", 30)
  temp_files_expiration_days = lookup(local.env.s3, "temp_expiration_days", 1)
  
  # Enable versioning for production
  enable_versioning = true
  
  # Use KMS encryption for production
  kms_key_arn = lookup(local.account.settings, "kms_key_arn", null)
  
  # Restricted CORS for production
  enable_cors          = true
  cors_allowed_origins = local.env.cors.allowed_origins
}
