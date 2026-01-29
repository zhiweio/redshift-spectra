# =============================================================================
# API Gateway Module - Terragrunt Configuration
# =============================================================================
# This module creates the REST API for the DaaS platform.
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
dependency "lambda" {
  config_path = "../lambda"
  
  mock_outputs = {
    api_function_name        = "mock-api-function"
    api_invoke_arn           = "arn:aws:lambda:us-east-1:123456789012:function:mock-api"
    authorizer_invoke_arn    = "arn:aws:lambda:us-east-1:123456789012:function:mock-authorizer"
    log_group_arns           = { api = "arn:aws:logs:us-east-1:123456789012:log-group:/aws/lambda/mock-api" }
  }
  mock_outputs_allowed_terraform_commands = ["validate", "plan"]
}

dependency "monitoring" {
  config_path = "../monitoring"
  
  mock_outputs = {
    api_gateway_log_group_arn = "arn:aws:logs:us-east-1:123456789012:log-group:/aws/api-gateway/mock"
  }
  mock_outputs_allowed_terraform_commands = ["validate", "plan"]
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
  
  # Authorization
  enable_lambda_authorizer     = true
  authorizer_lambda_invoke_arn = dependency.lambda.outputs.authorizer_invoke_arn
  
  # Logging
  access_log_group_arn = dependency.monitoring.outputs.api_gateway_log_group_arn
  
  # Throttling
  throttling_burst_limit = lookup(local.env.api_gateway, "throttling_burst_limit", local.common.api_gateway_defaults.throttling_burst_limit)
  throttling_rate_limit  = lookup(local.env.api_gateway, "throttling_rate_limit", local.common.api_gateway_defaults.throttling_rate_limit)
}
