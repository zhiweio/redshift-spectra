# =============================================================================
# Secrets Manager Module - Secure Credential Storage
# =============================================================================
# Creates Secrets Manager secrets for:
# - Redshift credentials (username/password)
# - JWT signing secret
# =============================================================================

# =============================================================================
# Redshift Credentials Secret
# =============================================================================

resource "aws_secretsmanager_secret" "redshift_credentials" {
  name        = "${var.name_prefix}/redshift-credentials"
  description = "Redshift database credentials for ${var.name_prefix}"

  recovery_window_in_days = var.recovery_window_in_days
  kms_key_id              = var.kms_key_arn

  tags = merge(var.tags, {
    Name = "${var.name_prefix}-redshift-credentials"
  })
}

resource "aws_secretsmanager_secret_version" "redshift_credentials" {
  secret_id = aws_secretsmanager_secret.redshift_credentials.id
  secret_string = jsonencode({
    username = var.redshift_username
    password = var.redshift_password
  })
}

# =============================================================================
# JWT Secret
# =============================================================================

resource "aws_secretsmanager_secret" "jwt_secret" {
  name        = "${var.name_prefix}/jwt-secret"
  description = "JWT signing secret for ${var.name_prefix} API authentication"

  recovery_window_in_days = var.recovery_window_in_days
  kms_key_id              = var.kms_key_arn

  tags = merge(var.tags, {
    Name = "${var.name_prefix}-jwt-secret"
  })
}

resource "aws_secretsmanager_secret_version" "jwt_secret" {
  secret_id = aws_secretsmanager_secret.jwt_secret.id
  secret_string = jsonencode({
    secret = var.jwt_secret
  })
}
