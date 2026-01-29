# =============================================================================
# DynamoDB Module - Production
# =============================================================================
# Inherits from dev configuration with production-specific settings.
# =============================================================================

include "root" {
  path = find_in_parent_folders()
}

include "common" {
  path   = find_in_parent_folders("common.hcl")
  expose = true
}

locals {
  env_vars = read_terragrunt_config(find_in_parent_folders("env.hcl"))
  env      = local.env_vars.locals.settings
  common   = include.common.locals
}

terraform {
  source = "${get_repo_root()}/terraform/modules/dynamodb"
}

inputs = {
  name_prefix = "${include.root.locals.project_name}-${include.root.locals.environment}"
  
  jobs_table_billing_mode      = lookup(local.env.dynamodb, "billing_mode", local.common.dynamodb_defaults.billing_mode)
  sessions_table_billing_mode  = lookup(local.env.dynamodb, "billing_mode", local.common.dynamodb_defaults.billing_mode)
  
  jobs_ttl_days      = lookup(local.env.dynamodb, "jobs_ttl_days", 30)
  sessions_ttl_hours = lookup(local.env.dynamodb, "sessions_ttl_hours", 8)
  
  # Enable point-in-time recovery for production
  enable_point_in_time_recovery = true
}
