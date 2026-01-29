# ============================================================================
# S3 Module Outputs
# ============================================================================

output "bucket_name" {
  description = "Name of the data S3 bucket"
  value       = aws_s3_bucket.data.id
}

output "bucket_arn" {
  description = "ARN of the data S3 bucket"
  value       = aws_s3_bucket.data.arn
}

output "bucket_domain_name" {
  description = "Domain name of the data S3 bucket"
  value       = aws_s3_bucket.data.bucket_domain_name
}

output "bucket_regional_domain_name" {
  description = "Regional domain name of the data S3 bucket"
  value       = aws_s3_bucket.data.bucket_regional_domain_name
}

output "logs_bucket_name" {
  description = "Name of the logs S3 bucket (if enabled)"
  value       = var.enable_access_logging ? aws_s3_bucket.logs[0].id : null
}

output "logs_bucket_arn" {
  description = "ARN of the logs S3 bucket (if enabled)"
  value       = var.enable_access_logging ? aws_s3_bucket.logs[0].arn : null
}

# S3 prefixes for different use cases
output "results_prefix" {
  description = "S3 prefix for query results"
  value       = "s3://${aws_s3_bucket.data.id}/results/"
}

output "bulk_exports_prefix" {
  description = "S3 prefix for bulk exports"
  value       = "s3://${aws_s3_bucket.data.id}/bulk/exports/"
}

output "bulk_imports_prefix" {
  description = "S3 prefix for bulk imports"
  value       = "s3://${aws_s3_bucket.data.id}/bulk/imports/"
}

output "temp_prefix" {
  description = "S3 prefix for temporary files"
  value       = "s3://${aws_s3_bucket.data.id}/temp/"
}
