# =============================================================================
# DynamoDB Module - Terragrunt Configuration (LocalStack)
# =============================================================================
# This module creates DynamoDB tables in LocalStack for local development.
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

# Load environment-specific configuration
locals {
  env_vars = read_terragrunt_config(find_in_parent_folders("env.hcl"))
  env      = local.env_vars.locals.settings

  common = include.common.locals
}

# Terraform module source
terraform {
  source = "${get_repo_root()}/terraform/modules/dynamodb"
}

# Module inputs
inputs = {
  # Use project name prefix for table naming
  name_prefix = "${include.root.locals.project_name}-${include.root.locals.environment}"

  # Billing configuration (LocalStack supports both modes)
  jobs_table_billing_mode   = lookup(local.env.dynamodb, "billing_mode", local.common.dynamodb_defaults.billing_mode)
  jobs_table_read_capacity  = lookup(local.env.dynamodb, "read_capacity", local.common.dynamodb_defaults.read_capacity)
  jobs_table_write_capacity = lookup(local.env.dynamodb, "write_capacity", local.common.dynamodb_defaults.write_capacity)

  sessions_table_billing_mode   = lookup(local.env.dynamodb, "billing_mode", local.common.dynamodb_defaults.billing_mode)
  sessions_table_read_capacity  = lookup(local.env.dynamodb, "read_capacity", local.common.dynamodb_defaults.read_capacity)
  sessions_table_write_capacity = lookup(local.env.dynamodb, "write_capacity", local.common.dynamodb_defaults.write_capacity)

  # TTL configuration (shorter for local dev)
  jobs_ttl_days      = lookup(local.env.dynamodb, "jobs_ttl_days", 1)
  sessions_ttl_hours = lookup(local.env.dynamodb, "sessions_ttl_hours", 1)
}
