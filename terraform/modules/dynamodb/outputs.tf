# ============================================================================
# DynamoDB Module Outputs
# ============================================================================

# Jobs Table
output "jobs_table_name" {
  description = "Name of the jobs DynamoDB table"
  value       = aws_dynamodb_table.jobs.name
}

output "jobs_table_arn" {
  description = "ARN of the jobs DynamoDB table"
  value       = aws_dynamodb_table.jobs.arn
}

output "jobs_table_id" {
  description = "ID of the jobs DynamoDB table"
  value       = aws_dynamodb_table.jobs.id
}

output "jobs_table_stream_arn" {
  description = "Stream ARN of the jobs DynamoDB table"
  value       = aws_dynamodb_table.jobs.stream_arn
}

# Sessions Table
output "sessions_table_name" {
  description = "Name of the sessions DynamoDB table"
  value       = aws_dynamodb_table.sessions.name
}

output "sessions_table_arn" {
  description = "ARN of the sessions DynamoDB table"
  value       = aws_dynamodb_table.sessions.arn
}

output "sessions_table_id" {
  description = "ID of the sessions DynamoDB table"
  value       = aws_dynamodb_table.sessions.id
}

# Bulk Jobs Table
output "bulk_jobs_table_name" {
  description = "Name of the bulk jobs DynamoDB table"
  value       = aws_dynamodb_table.bulk_jobs.name
}

output "bulk_jobs_table_arn" {
  description = "ARN of the bulk jobs DynamoDB table"
  value       = aws_dynamodb_table.bulk_jobs.arn
}

output "bulk_jobs_table_id" {
  description = "ID of the bulk jobs DynamoDB table"
  value       = aws_dynamodb_table.bulk_jobs.id
}

# All Table ARNs (for IAM policies)
output "all_table_arns" {
  description = "List of all DynamoDB table ARNs"
  value = [
    aws_dynamodb_table.jobs.arn,
    aws_dynamodb_table.sessions.arn,
    aws_dynamodb_table.bulk_jobs.arn,
  ]
}
