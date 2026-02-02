# =============================================================================
# Lambda Module - Variables
# =============================================================================

variable "name_prefix" {
  description = "Prefix for resource names"
  type        = string
}

variable "region" {
  description = "AWS region"
  type        = string
  default     = null
}

variable "account_id" {
  description = "AWS account ID"
  type        = string
  default     = null
}

variable "tags" {
  description = "Tags to apply to all resources"
  type        = map(string)
  default     = {}
}

# =============================================================================
# Runtime Configuration
# =============================================================================

variable "python_runtime" {
  description = "Python runtime version"
  type        = string
  default     = "python3.11"
}

variable "lambda_timeout" {
  description = "Default Lambda timeout in seconds"
  type        = number
  default     = 30
}

variable "lambda_memory_size" {
  description = "Default Lambda memory size in MB"
  type        = number
  default     = 256
}

variable "worker_timeout" {
  description = "Worker Lambda timeout in seconds"
  type        = number
  default     = 900
}

variable "worker_memory_size" {
  description = "Worker Lambda memory size in MB"
  type        = number
  default     = 1024
}

variable "log_level" {
  description = "Log level for Lambda functions"
  type        = string
  default     = "INFO"
}

variable "log_retention_days" {
  description = "CloudWatch log retention in days"
  type        = number
  default     = 30
}

# =============================================================================
# Deployment Packages
# =============================================================================

variable "authorizer_package_path" {
  description = "Path to authorizer Lambda deployment package"
  type        = string
}

variable "api_package_path" {
  description = "Path to API handler Lambda deployment package"
  type        = string
}

variable "worker_package_path" {
  description = "Path to worker Lambda deployment package"
  type        = string
}

variable "layer_package_path" {
  description = "Path to Lambda layer package"
  type        = string
  default     = null
}

variable "create_layer" {
  description = "Whether to create a Lambda layer"
  type        = bool
  default     = false
}

variable "lambda_layer_arn" {
  description = "ARN of existing Lambda layer to use"
  type        = string
  default     = null
}

# =============================================================================
# IAM Roles
# =============================================================================

variable "authorizer_role_arn" {
  description = "IAM role ARN for authorizer Lambda"
  type        = string
}

variable "api_role_arn" {
  description = "IAM role ARN for API handler Lambda"
  type        = string
}

variable "worker_role_arn" {
  description = "IAM role ARN for worker Lambda"
  type        = string
}

# =============================================================================
# Environment Variables
# =============================================================================

variable "environment" {
  description = "Environment name (local, dev, prod)"
  type        = string
  default     = "dev"
}

variable "environment_variables" {
  description = "Additional environment variables for Lambda functions"
  type        = map(string)
  default     = {}
}

# =============================================================================
# Redshift Configuration
# =============================================================================

variable "redshift_cluster_id" {
  description = "Redshift cluster identifier"
  type        = string
  default     = ""
}

variable "redshift_database" {
  description = "Redshift database name"
  type        = string
  default     = "dev"
}

variable "redshift_workgroup_name" {
  description = "Redshift Serverless workgroup name"
  type        = string
  default     = "default"
}

variable "redshift_secret_arn" {
  description = "ARN of Redshift credentials secret in Secrets Manager"
  type        = string
  default     = ""
}

variable "redshift_session_keep_alive_seconds" {
  description = "Redshift session keep-alive interval in seconds"
  type        = number
  default     = 3600
}

variable "redshift_session_idle_timeout_seconds" {
  description = "Redshift session idle timeout in seconds"
  type        = number
  default     = 300
}

# =============================================================================
# DynamoDB Configuration
# =============================================================================

variable "dynamodb_table_name" {
  description = "DynamoDB jobs table name"
  type        = string
  default     = ""
}

variable "dynamodb_sessions_table_name" {
  description = "DynamoDB sessions table name"
  type        = string
  default     = ""
}

variable "dynamodb_bulk_table_name" {
  description = "DynamoDB bulk jobs table name"
  type        = string
  default     = ""
}

# =============================================================================
# S3 Configuration
# =============================================================================

variable "s3_bucket_name" {
  description = "S3 bucket name for data storage"
  type        = string
  default     = ""
}

variable "s3_use_path_style" {
  description = "Use path-style S3 URLs (required for LocalStack)"
  type        = bool
  default     = false
}

# =============================================================================
# Authentication Configuration
# =============================================================================

variable "auth_mode" {
  description = "Authentication mode (jwt or iam)"
  type        = string
  default     = "jwt"
}

variable "jwt_secret_arn" {
  description = "ARN of JWT secret in Secrets Manager"
  type        = string
  default     = ""
}

variable "jwt_expiry_hours" {
  description = "JWT token expiry in hours"
  type        = number
  default     = 24
}

variable "jwt_issuer" {
  description = "JWT issuer claim"
  type        = string
  default     = "redshift-spectra"
}

variable "jwt_audience" {
  description = "JWT audience claim"
  type        = string
  default     = "redshift-spectra-api"
}

# =============================================================================
# LocalStack Configuration
# =============================================================================

variable "is_localstack" {
  description = "Whether running in LocalStack environment"
  type        = bool
  default     = false
}

variable "localstack_hostname" {
  description = "LocalStack hostname (use host.docker.internal for Lambda containers)"
  type        = string
  default     = "host.docker.internal"
}

variable "aws_endpoint_url" {
  description = "AWS endpoint URL (for LocalStack)"
  type        = string
  default     = ""
}

# =============================================================================
# VPC Configuration
# =============================================================================

variable "vpc_subnet_ids" {
  description = "VPC subnet IDs for Lambda"
  type        = list(string)
  default     = []
}

variable "vpc_security_group_ids" {
  description = "VPC security group IDs for Lambda"
  type        = list(string)
  default     = []
}

# =============================================================================
# API Gateway Integration
# =============================================================================

variable "api_gateway_execution_arn" {
  description = "API Gateway execution ARN for Lambda permissions"
  type        = string
  default     = "*"
}

# =============================================================================
# Concurrency & Scaling
# =============================================================================

variable "authorizer_reserved_concurrency" {
  description = "Reserved concurrency for authorizer Lambda"
  type        = number
  default     = -1
}

variable "api_reserved_concurrency" {
  description = "Reserved concurrency for API Lambda"
  type        = number
  default     = -1
}

variable "worker_reserved_concurrency" {
  description = "Reserved concurrency for worker Lambda"
  type        = number
  default     = -1
}

# =============================================================================
# Observability
# =============================================================================

variable "enable_xray" {
  description = "Enable X-Ray tracing"
  type        = bool
  default     = true
}

variable "kms_key_arn" {
  description = "KMS key ARN for CloudWatch log encryption"
  type        = string
  default     = null
}

# =============================================================================
# Event Sources
# =============================================================================

variable "enable_dynamodb_trigger" {
  description = "Enable DynamoDB stream trigger for worker"
  type        = bool
  default     = true
}

variable "dynamodb_stream_arn" {
  description = "DynamoDB stream ARN for worker trigger"
  type        = string
  default     = null
}

variable "dynamodb_batch_size" {
  description = "Batch size for DynamoDB trigger"
  type        = number
  default     = 10
}

variable "dynamodb_batch_window" {
  description = "Batch window for DynamoDB trigger in seconds"
  type        = number
  default     = 5
}

variable "dlq_arn" {
  description = "Dead letter queue ARN for failed invocations"
  type        = string
  default     = null
}

# =============================================================================
# Bulk Processing
# =============================================================================

variable "enable_bulk_processing" {
  description = "Enable bulk data processing features"
  type        = bool
  default     = true
}

variable "max_batch_size" {
  description = "Maximum batch size for bulk operations"
  type        = number
  default     = 10000
}
