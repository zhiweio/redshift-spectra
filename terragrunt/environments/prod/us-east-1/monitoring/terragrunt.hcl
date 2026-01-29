# =============================================================================
# Monitoring Module - Production
# =============================================================================
# Creates CloudWatch dashboards, alarms, and API Gateway log groups.
# Depends on Lambda for function names and log group references.
# =============================================================================

include "root" {
  path = find_in_parent_folders()
}

include "common" {
  path   = find_in_parent_folders("common.hcl")
  expose = true
}

# Dependencies
dependency "lambda" {
  config_path = "../lambda"
  mock_outputs = {
    api_function_name        = "mock-api-function"
    worker_function_name     = "mock-worker-function"
    authorizer_function_name = "mock-authorizer-function"
  }
  mock_outputs_allowed_terraform_commands = ["validate", "plan"]
}

locals {
  region_vars = read_terragrunt_config(find_in_parent_folders("region.hcl"))
  env_vars    = read_terragrunt_config(find_in_parent_folders("env.hcl"))
  
  region = local.region_vars.locals
  env    = local.env_vars.locals.settings
  common = include.common.locals
}

terraform {
  source = "${get_repo_root()}/terraform/modules/monitoring"
}

inputs = {
  project_name = include.root.locals.project_name
  environment  = include.root.locals.environment
  aws_region   = local.region.aws_region
  
  # Longer log retention for production
  log_retention_days = lookup(local.env.monitoring, "log_retention_days", 90)
  
  # Lambda function names (from Lambda module outputs)
  lambda_function_names = {
    api        = dependency.lambda.outputs.api_function_name
    worker     = dependency.lambda.outputs.worker_function_name
    authorizer = dependency.lambda.outputs.authorizer_function_name
  }
  
  # Lambda log group names for CloudWatch Insights
  lambda_log_group_names = {
    api        = "/aws/lambda/${dependency.lambda.outputs.api_function_name}"
    worker     = "/aws/lambda/${dependency.lambda.outputs.worker_function_name}"
    authorizer = "/aws/lambda/${dependency.lambda.outputs.authorizer_function_name}"
  }
  
  # Stricter alarm thresholds for production
  lambda_error_threshold       = lookup(local.env.monitoring, "lambda_error_threshold", 3)
  lambda_duration_threshold_ms = lookup(local.env.monitoring, "lambda_duration_threshold_ms", 10000)
  api_error_threshold          = lookup(local.env.monitoring, "api_5xx_error_threshold", 3)
  api_latency_threshold_ms     = lookup(local.env.monitoring, "api_latency_threshold_ms", 5000)
  
  # Enable alerting for production
  create_sns_topic = true
  alert_email      = lookup(local.env.monitoring, "alert_email", null)
  
  # X-Ray tracing enabled
  enable_xray_tracing = true
}
