# =============================================================================
# Secrets Manager Module - Outputs
# =============================================================================

output "redshift_credentials_secret_arn" {
  description = "ARN of the Redshift credentials secret"
  value       = aws_secretsmanager_secret.redshift_credentials.arn
}

output "redshift_credentials_secret_name" {
  description = "Name of the Redshift credentials secret"
  value       = aws_secretsmanager_secret.redshift_credentials.name
}

output "jwt_secret_arn" {
  description = "ARN of the JWT signing secret"
  value       = aws_secretsmanager_secret.jwt_secret.arn
}

output "jwt_secret_name" {
  description = "Name of the JWT signing secret"
  value       = aws_secretsmanager_secret.jwt_secret.name
}
