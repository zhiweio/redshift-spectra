# =============================================================================
# Lambda Module - Terragrunt Configuration (LocalStack)
# =============================================================================
# This module creates Lambda functions in LocalStack for local development.
# Note: LocalStack supports Lambda execution via Docker or local runtime.
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

# Dependencies
dependency "iam" {
  config_path = "../iam"

  mock_outputs = {
    authorizer_role_arn  = "arn:aws:iam::000000000000:role/mock-authorizer-role"
    api_handler_role_arn = "arn:aws:iam::000000000000:role/mock-api-role"
    worker_role_arn      = "arn:aws:iam::000000000000:role/mock-worker-role"
  }
  mock_outputs_allowed_terraform_commands = ["init", "validate", "plan"]
}

dependency "dynamodb" {
  config_path = "../dynamodb"

  mock_outputs = {
    jobs_table_name       = "mock-jobs-table"
    sessions_table_name   = "mock-sessions-table"
    jobs_table_stream_arn = "arn:aws:dynamodb:us-east-1:000000000000:table/mock-jobs/stream/2024-01-01T00:00:00.000"
  }
  mock_outputs_allowed_terraform_commands = ["init", "validate", "plan"]
}

dependency "s3" {
  config_path = "../s3"

  mock_outputs = {
    bucket_name = "mock-bucket"
  }
  mock_outputs_allowed_terraform_commands = ["init", "validate", "plan"]
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

  # LocalStack endpoint for environment variables
  localstack_endpoint = local.region.localstack.endpoint
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

  # Runtime configuration (optimized for LocalStack debugging)
  python_runtime     = lookup(local.env.lambda, "python_runtime", local.common.lambda_defaults.python_runtime)
  lambda_timeout     = lookup(local.env.lambda, "timeout", local.common.lambda_defaults.timeout)
  lambda_memory_size = lookup(local.env.lambda, "memory_size", local.common.lambda_defaults.memory_size)
  log_level          = lookup(local.env.lambda, "log_level", "DEBUG")

  # Shorter log retention for local dev
  log_retention_days = lookup(local.env.monitoring, "log_retention_days", 1)

  # Lambda Layer - shared dependencies
  create_layer       = true
  layer_package_path = "${local.lambda_dist_dir}/layer.zip"

  # Function packages (code only)
  authorizer_package_path = "${local.lambda_dist_dir}/authorizer.zip"
  api_package_path        = "${local.lambda_dist_dir}/api-handler.zip"
  worker_package_path     = "${local.lambda_dist_dir}/worker.zip"

  # IAM roles (LocalStack IAM is permissive by default)
  authorizer_role_arn = dependency.iam.outputs.authorizer_role_arn
  api_role_arn        = dependency.iam.outputs.api_handler_role_arn
  worker_role_arn     = dependency.iam.outputs.worker_role_arn

  # Environment variables for LocalStack
  environment_variables = {
    ENVIRONMENT                                   = include.root.locals.environment
    SPECTRA_DYNAMODB_TABLE_NAME                   = dependency.dynamodb.outputs.jobs_table_name
    SPECTRA_DYNAMODB_SESSIONS_TABLE_NAME          = dependency.dynamodb.outputs.sessions_table_name
    SPECTRA_S3_BUCKET_NAME                        = dependency.s3.outputs.bucket_name
    SPECTRA_REDSHIFT_WORKGROUP_NAME               = local.env.redshift.workgroup_name
    SPECTRA_REDSHIFT_DATABASE                     = local.env.redshift.database
    SPECTRA_REDSHIFT_SESSION_KEEP_ALIVE_SECONDS   = "3600"
    SPECTRA_REDSHIFT_SESSION_IDLE_TIMEOUT_SECONDS = "300"

    # LocalStack-specific environment variables
    IS_LOCALSTACK       = "true"
    LOCALSTACK_HOSTNAME = "localhost"
    AWS_ENDPOINT_URL    = local.localstack_endpoint

    # Use path-style S3 URLs for LocalStack
    AWS_S3_USE_PATH_STYLE = "true"
  }

  # DynamoDB Stream trigger for worker
  # Disabled for LocalStack - DynamoDB Streams event source mapping not fully supported
  enable_dynamodb_trigger = false
  dynamodb_stream_arn     = ""

  # No VPC in LocalStack
  vpc_subnet_ids         = []
  vpc_security_group_ids = []

  # Disable X-Ray for LocalStack (not fully supported)
  enable_xray = false

  # No KMS in LocalStack
  kms_key_arn = null

  # No reserved concurrency limits for local dev
  authorizer_reserved_concurrency = -1
  api_reserved_concurrency        = -1
  worker_reserved_concurrency     = -1

  # JWT configuration (relaxed for local development)
  jwt_secret_arn   = null
  jwt_expiry_hours = lookup(local.env.security, "jwt_expiry_hours", 720)
}
