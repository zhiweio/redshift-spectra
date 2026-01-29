# =============================================================================
# Lambda Module - Terragrunt Configuration
# =============================================================================
# This module creates Lambda functions (API, Worker, Authorizer) with shared layer.
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

# Dependencies
dependency "iam" {
  config_path = "../iam"
  
  mock_outputs = {
    authorizer_role_arn  = "arn:aws:iam::123456789012:role/mock-authorizer-role"
    api_handler_role_arn = "arn:aws:iam::123456789012:role/mock-api-role"
    worker_role_arn      = "arn:aws:iam::123456789012:role/mock-worker-role"
  }
  mock_outputs_allowed_terraform_commands = ["validate", "plan"]
}

dependency "dynamodb" {
  config_path = "../dynamodb"
  
  mock_outputs = {
    jobs_table_name       = "mock-jobs-table"
    sessions_table_name   = "mock-sessions-table"
    jobs_table_stream_arn = "arn:aws:dynamodb:us-east-1:123456789012:table/mock-jobs/stream/2024-01-01T00:00:00.000"
  }
  mock_outputs_allowed_terraform_commands = ["validate", "plan"]
}

dependency "s3" {
  config_path = "../s3"
  
  mock_outputs = {
    bucket_name = "mock-bucket"
  }
  mock_outputs_allowed_terraform_commands = ["validate", "plan"]
}

# Load configuration
locals {
  account_vars = read_terragrunt_config(find_in_parent_folders("account.hcl"))
  region_vars  = read_terragrunt_config(find_in_parent_folders("region.hcl"))
  env_vars     = read_terragrunt_config(find_in_parent_folders("env.hcl"))
  
  account = local.account_vars.locals
  region  = local.region_vars.locals
  env     = local.env_vars.locals.settings
  
  common = include.common.locals
  
  # Lambda package paths (relative to terragrunt directory)
  lambda_dist_dir = "${get_repo_root()}/dist/lambda"
}

# Terraform module source
terraform {
  source = "${get_repo_root()}/terraform/modules/lambda"
}

# Module inputs
inputs = {
  name_prefix = "${include.root.locals.project_name}-${include.root.locals.environment}"
  region      = local.region.aws_region
  account_id  = local.account.account_id
  
  # Runtime configuration
  python_runtime     = lookup(local.env.lambda, "python_runtime", local.common.lambda_defaults.python_runtime)
  lambda_timeout     = lookup(local.env.lambda, "timeout", local.common.lambda_defaults.timeout)
  lambda_memory_size = lookup(local.env.lambda, "memory_size", local.common.lambda_defaults.memory_size)
  log_level          = lookup(local.env.lambda, "log_level", local.common.lambda_defaults.log_level)
  
  # Lambda Layer - shared dependencies
  create_layer       = true
  layer_package_path = "${local.lambda_dist_dir}/layer.zip"
  
  # Function packages (code only)
  authorizer_package_path = "${local.lambda_dist_dir}/authorizer.zip"
  api_package_path        = "${local.lambda_dist_dir}/api-handler.zip"
  worker_package_path     = "${local.lambda_dist_dir}/worker.zip"
  
  # IAM roles
  authorizer_role_arn = dependency.iam.outputs.authorizer_role_arn
  api_role_arn        = dependency.iam.outputs.api_handler_role_arn
  worker_role_arn     = dependency.iam.outputs.worker_role_arn
  
  # Environment variables
  environment_variables = {
    ENVIRONMENT                            = include.root.locals.environment
    SPECTRA_DYNAMODB_TABLE_NAME            = dependency.dynamodb.outputs.jobs_table_name
    SPECTRA_DYNAMODB_SESSIONS_TABLE_NAME   = dependency.dynamodb.outputs.sessions_table_name
    SPECTRA_S3_BUCKET_NAME                 = dependency.s3.outputs.bucket_name
    SPECTRA_REDSHIFT_WORKGROUP_NAME        = local.env.redshift.workgroup_name
    SPECTRA_REDSHIFT_DATABASE              = local.env.redshift.database
    SPECTRA_REDSHIFT_SESSION_KEEP_ALIVE_SECONDS = lookup(local.env, "redshift_session_keep_alive_seconds", 3600)
    SPECTRA_REDSHIFT_SESSION_IDLE_TIMEOUT_SECONDS = lookup(local.env, "redshift_session_idle_timeout_seconds", 300)
  }
  
  # DynamoDB Stream trigger for worker
  enable_dynamodb_trigger = true
  dynamodb_stream_arn     = dependency.dynamodb.outputs.jobs_table_stream_arn
  
  # VPC configuration (if enabled)
  vpc_subnet_ids         = lookup(local.account.settings, "subnet_ids", [])
  vpc_security_group_ids = []
}
