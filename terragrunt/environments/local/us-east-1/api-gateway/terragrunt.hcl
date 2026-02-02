# =============================================================================
# API Gateway Module - Terragrunt Configuration (LocalStack)
# =============================================================================
# This module creates the REST API in LocalStack for local development.
# Note: LocalStack supports API Gateway REST APIs with Lambda integrations.
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
dependency "lambda" {
  config_path = "../lambda"

  mock_outputs = {
    api_function_name     = "mock-api-function"
    api_invoke_arn        = "arn:aws:lambda:us-east-1:000000000000:function:mock-api"
    authorizer_invoke_arn = "arn:aws:lambda:us-east-1:000000000000:function:mock-authorizer"
    log_group_arns        = { api = "arn:aws:logs:us-east-1:000000000000:log-group:/aws/lambda/mock-api" }
  }
  mock_outputs_allowed_terraform_commands = ["init", "validate", "plan"]
}

dependency "monitoring" {
  config_path = "../monitoring"

  mock_outputs = {
    api_gateway_log_group_arn = "arn:aws:logs:us-east-1:000000000000:log-group:/aws/api-gateway/mock"
  }
  mock_outputs_allowed_terraform_commands = ["init", "validate", "plan"]
}

# Load configuration
locals {
  env_vars = read_terragrunt_config(find_in_parent_folders("env.hcl"))
  env      = local.env_vars.locals.settings

  common = include.common.locals
}

# Terraform module source
terraform {
  source = "${get_repo_root()}/terraform/modules/api-gateway"
}

# Module inputs
inputs = {
  project_name = include.root.locals.project_name
  environment  = include.root.locals.environment

  # Lambda integrations - using single API handler for all endpoints
  query_lambda_invoke_arn     = dependency.lambda.outputs.api_invoke_arn
  query_lambda_function_name  = dependency.lambda.outputs.api_function_name
  status_lambda_invoke_arn    = dependency.lambda.outputs.api_invoke_arn
  status_lambda_function_name = dependency.lambda.outputs.api_function_name
  result_lambda_invoke_arn    = dependency.lambda.outputs.api_invoke_arn
  result_lambda_function_name = dependency.lambda.outputs.api_function_name
  bulk_lambda_invoke_arn      = dependency.lambda.outputs.api_invoke_arn
  bulk_lambda_function_name   = dependency.lambda.outputs.api_function_name

  # Disable Lambda authorizer for simpler local development
  # (can be enabled if needed for authorization testing)
  enable_lambda_authorizer     = false
  authorizer_lambda_invoke_arn = dependency.lambda.outputs.authorizer_invoke_arn

  # Logging
  access_log_group_arn = dependency.monitoring.outputs.api_gateway_log_group_arn

  # No throttling for local development
  throttling_burst_limit = lookup(local.env.api_gateway, "throttling_burst_limit", 1000)
  throttling_rate_limit  = lookup(local.env.api_gateway, "throttling_rate_limit", 1000)
}
