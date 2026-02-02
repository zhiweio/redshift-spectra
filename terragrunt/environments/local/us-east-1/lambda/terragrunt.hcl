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
    bulk_jobs_table_name  = "mock-bulk-jobs-table"
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

dependency "secrets_manager" {
  config_path = "../secrets-manager"

  mock_outputs = {
    redshift_credentials_secret_arn = "arn:aws:secretsmanager:us-east-1:000000000000:secret:mock-redshift-credentials"
    jwt_secret_arn                  = "arn:aws:secretsmanager:us-east-1:000000000000:secret:mock-jwt-secret"
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
  # Use host.docker.internal for Lambda containers to reach LocalStack on macOS/Windows
  localstack_endpoint    = local.region.localstack.endpoint
  localstack_docker_host = "http://host.docker.internal:4566"
  localstack_hostname    = "host.docker.internal"
}

# Terraform module source
terraform {
  source = "${get_repo_root()}/terraform/modules/lambda"
}

# Module inputs
inputs = {
  name_prefix = "${include.root.locals.project_name}-${include.root.locals.environment}"
  environment = include.root.locals.environment
  region      = local.region.aws_region
  account_id  = local.account.account_id

  # Runtime configuration (optimized for LocalStack debugging)
  python_runtime     = lookup(local.env.lambda, "python_runtime", local.common.lambda_defaults.python_runtime)
  lambda_timeout     = lookup(local.env.lambda, "timeout", local.common.lambda_defaults.timeout)
  lambda_memory_size = lookup(local.env.lambda, "memory_size", local.common.lambda_defaults.memory_size)
  log_level          = lookup(local.env.lambda, "log_level", "DEBUG")

  # Shorter log retention for local dev
  log_retention_days = lookup(local.env.monitoring, "log_retention_days", 1)

  # Lambda Layer - disabled for LocalStack (Lambda Layers not fully supported)
  # LocalStack community edition doesn't properly load layer content into Python path.
  # Instead, we use "fat" Lambda packages that include all dependencies.
  create_layer       = false
  layer_package_path = null

  # Fat Lambda packages (include all dependencies, no layer needed)
  # Built with: make package-lambda-fat
  authorizer_package_path = "${local.lambda_dist_dir}/authorizer-fat.zip"
  api_package_path        = "${local.lambda_dist_dir}/api-handler-fat.zip"
  worker_package_path     = "${local.lambda_dist_dir}/worker-fat.zip"

  # IAM roles (LocalStack IAM is permissive by default)
  authorizer_role_arn = dependency.iam.outputs.authorizer_role_arn
  api_role_arn        = dependency.iam.outputs.api_handler_role_arn
  worker_role_arn     = dependency.iam.outputs.worker_role_arn

  # ==========================================================================
  # Redshift Configuration
  # ==========================================================================
  redshift_cluster_id                   = "local-cluster"
  redshift_database                     = local.env.redshift.database
  redshift_workgroup_name               = local.env.redshift.workgroup_name
  redshift_secret_arn                   = dependency.secrets_manager.outputs.redshift_credentials_secret_arn
  redshift_session_keep_alive_seconds   = 3600
  redshift_session_idle_timeout_seconds = 300

  # ==========================================================================
  # DynamoDB Configuration
  # ==========================================================================
  dynamodb_table_name          = dependency.dynamodb.outputs.jobs_table_name
  dynamodb_sessions_table_name = dependency.dynamodb.outputs.sessions_table_name
  dynamodb_bulk_table_name     = dependency.dynamodb.outputs.bulk_jobs_table_name

  # ==========================================================================
  # S3 Configuration
  # ==========================================================================
  s3_bucket_name    = dependency.s3.outputs.bucket_name
  s3_use_path_style = true

  # ==========================================================================
  # Authentication Configuration
  # ==========================================================================
  auth_mode        = "jwt"
  jwt_secret_arn   = dependency.secrets_manager.outputs.jwt_secret_arn
  jwt_issuer       = "redshift-spectra-local"
  jwt_audience     = "redshift-spectra-api"
  jwt_expiry_hours = lookup(local.env.security, "jwt_expiry_hours", 720)

  # ==========================================================================
  # LocalStack Configuration
  # ==========================================================================
  is_localstack       = true
  localstack_hostname = local.localstack_hostname
  aws_endpoint_url    = local.localstack_docker_host

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

  tags = include.root.locals.common_tags
}
