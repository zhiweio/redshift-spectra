# ============================================================================
# IAM Module Outputs
# ============================================================================

output "authorizer_role_arn" {
  description = "ARN of the authorizer Lambda execution role"
  value       = aws_iam_role.authorizer.arn
}

output "authorizer_role_name" {
  description = "Name of the authorizer Lambda execution role"
  value       = aws_iam_role.authorizer.name
}

output "api_handler_role_arn" {
  description = "ARN of the API handler Lambda execution role"
  value       = aws_iam_role.api_handler.arn
}

output "api_handler_role_name" {
  description = "Name of the API handler Lambda execution role"
  value       = aws_iam_role.api_handler.name
}

output "worker_role_arn" {
  description = "ARN of the worker Lambda execution role"
  value       = aws_iam_role.worker.arn
}

output "worker_role_name" {
  description = "Name of the worker Lambda execution role"
  value       = aws_iam_role.worker.name
}

output "redshift_s3_role_arn" {
  description = "ARN of the Redshift S3 access role"
  value       = aws_iam_role.redshift_s3.arn
}
