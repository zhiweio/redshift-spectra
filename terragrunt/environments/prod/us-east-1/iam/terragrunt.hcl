# =============================================================================
# IAM Module - Production
# =============================================================================

include "root" {
  path = find_in_parent_folders()
}

dependency "dynamodb" {
  config_path = "../dynamodb"
  mock_outputs = {
    jobs_table_arn      = "arn:aws:dynamodb:us-east-1:987654321098:table/mock-jobs"
    sessions_table_arn  = "arn:aws:dynamodb:us-east-1:987654321098:table/mock-sessions"
    bulk_jobs_table_arn = "arn:aws:dynamodb:us-east-1:987654321098:table/mock-bulk-jobs"
    all_table_arns = [
      "arn:aws:dynamodb:us-east-1:987654321098:table/mock-jobs",
      "arn:aws:dynamodb:us-east-1:987654321098:table/mock-sessions",
      "arn:aws:dynamodb:us-east-1:987654321098:table/mock-bulk-jobs"
    ]
  }
  mock_outputs_allowed_terraform_commands = ["init", "validate", "plan"]
}

dependency "s3" {
  config_path = "../s3"
  mock_outputs = {
    bucket_arn = "arn:aws:s3:::mock-bucket"
  }
  mock_outputs_allowed_terraform_commands = ["validate", "plan"]
}

locals {
  account_vars = read_terragrunt_config(find_in_parent_folders("account.hcl"))
  region_vars  = read_terragrunt_config(find_in_parent_folders("region.hcl"))
  env_vars     = read_terragrunt_config(find_in_parent_folders("env.hcl"))

  account = local.account_vars.locals
  region  = local.region_vars.locals
  env     = local.env_vars.locals.settings
}

terraform {
  source = "${get_repo_root()}/terraform/modules/iam"
}

inputs = {
  name_prefix = "${include.root.locals.project_name}-${include.root.locals.environment}"

  redshift_workgroup_arn = "arn:aws:redshift-serverless:${local.region.aws_region}:${local.account.account_id}:workgroup/${local.env.redshift.workgroup_name}"
  redshift_namespace_arn = "arn:aws:redshift-serverless:${local.region.aws_region}:${local.account.account_id}:namespace/*"

  # DynamoDB access (all tables including bulk_jobs)
  dynamodb_table_arns = dependency.dynamodb.outputs.all_table_arns

  s3_bucket_arn      = dependency.s3.outputs.bucket_arn
  secrets_arn_prefix = "arn:aws:secretsmanager:${local.region.aws_region}:${local.account.account_id}:secret:${include.root.locals.project_name}/*"
  kms_key_arn        = lookup(local.account.settings, "kms_key_arn", null)
}
