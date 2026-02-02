# =============================================================================
# Secrets Manager Module - Variables
# =============================================================================

variable "name_prefix" {
  description = "Prefix for resource names"
  type        = string
}

variable "tags" {
  description = "Tags to apply to all resources"
  type        = map(string)
  default     = {}
}

# =============================================================================
# Redshift Credentials
# =============================================================================

variable "redshift_username" {
  description = "Redshift database username"
  type        = string
  sensitive   = true
}

variable "redshift_password" {
  description = "Redshift database password"
  type        = string
  sensitive   = true
}

# =============================================================================
# JWT Configuration
# =============================================================================

variable "jwt_secret" {
  description = "JWT signing secret (minimum 32 characters recommended)"
  type        = string
  sensitive   = true
}

# =============================================================================
# Encryption
# =============================================================================

variable "kms_key_arn" {
  description = "KMS key ARN for encrypting secrets (uses AWS managed key if null)"
  type        = string
  default     = null
}

# =============================================================================
# Recovery Configuration
# =============================================================================

variable "recovery_window_in_days" {
  description = "Number of days before secret can be deleted (0 for immediate deletion)"
  type        = number
  default     = 7
}
