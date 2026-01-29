# ============================================================================
# DynamoDB Module - State Management Tables for Redshift Spectra
# ============================================================================

# ============================================================================
# Jobs Table - Query and Bulk Job State Management
# ============================================================================

resource "aws_dynamodb_table" "jobs" {
  name         = "${var.name_prefix}-jobs"
  billing_mode = var.jobs_table_billing_mode

  # Provisioned capacity (only used when billing_mode = "PROVISIONED")
  read_capacity  = var.jobs_table_billing_mode == "PROVISIONED" ? var.jobs_table_read_capacity : null
  write_capacity = var.jobs_table_billing_mode == "PROVISIONED" ? var.jobs_table_write_capacity : null

  # Primary key
  hash_key  = "pk"          # tenant_id
  range_key = "sk"          # job_id

  # Attributes
  attribute {
    name = "pk"
    type = "S"
  }

  attribute {
    name = "sk"
    type = "S"
  }

  attribute {
    name = "job_state"
    type = "S"
  }

  attribute {
    name = "created_at"
    type = "S"
  }

  attribute {
    name = "redshift_query_id"
    type = "S"
  }

  # Global Secondary Indexes

  # GSI1: Query by job state (for monitoring/admin)
  global_secondary_index {
    name            = "gsi1-state"
    hash_key        = "pk"
    range_key       = "job_state"
    projection_type = "ALL"

    read_capacity  = var.jobs_table_billing_mode == "PROVISIONED" ? var.jobs_table_read_capacity : null
    write_capacity = var.jobs_table_billing_mode == "PROVISIONED" ? var.jobs_table_write_capacity : null
  }

  # GSI2: Query by creation time (for listing/pagination)
  global_secondary_index {
    name            = "gsi2-created"
    hash_key        = "pk"
    range_key       = "created_at"
    projection_type = "ALL"

    read_capacity  = var.jobs_table_billing_mode == "PROVISIONED" ? var.jobs_table_read_capacity : null
    write_capacity = var.jobs_table_billing_mode == "PROVISIONED" ? var.jobs_table_write_capacity : null
  }

  # GSI3: Query by Redshift query ID (for async result correlation)
  global_secondary_index {
    name            = "gsi3-redshift-query"
    hash_key        = "redshift_query_id"
    projection_type = "ALL"

    read_capacity  = var.jobs_table_billing_mode == "PROVISIONED" ? var.jobs_table_read_capacity : null
    write_capacity = var.jobs_table_billing_mode == "PROVISIONED" ? var.jobs_table_write_capacity : null
  }

  # TTL configuration
  ttl {
    attribute_name = "ttl"
    enabled        = true
  }

  # Point-in-time recovery
  point_in_time_recovery {
    enabled = var.enable_point_in_time_recovery
  }

  # Server-side encryption
  server_side_encryption {
    enabled     = true
    kms_key_arn = var.kms_key_arn
  }

  tags = merge(var.tags, {
    Name = "${var.name_prefix}-jobs"
  })
}

# ============================================================================
# Sessions Table - Tenant Session Cache
# ============================================================================

resource "aws_dynamodb_table" "sessions" {
  name         = "${var.name_prefix}-sessions"
  billing_mode = var.sessions_table_billing_mode

  # Provisioned capacity
  read_capacity  = var.sessions_table_billing_mode == "PROVISIONED" ? var.sessions_table_read_capacity : null
  write_capacity = var.sessions_table_billing_mode == "PROVISIONED" ? var.sessions_table_write_capacity : null

  # Primary key
  hash_key = "session_id"

  attribute {
    name = "session_id"
    type = "S"
  }

  attribute {
    name = "tenant_id"
    type = "S"
  }

  # GSI: Query sessions by tenant
  global_secondary_index {
    name            = "gsi1-tenant"
    hash_key        = "tenant_id"
    projection_type = "ALL"

    read_capacity  = var.sessions_table_billing_mode == "PROVISIONED" ? var.sessions_table_read_capacity : null
    write_capacity = var.sessions_table_billing_mode == "PROVISIONED" ? var.sessions_table_write_capacity : null
  }

  # TTL configuration
  ttl {
    attribute_name = "ttl"
    enabled        = true
  }

  # Point-in-time recovery
  point_in_time_recovery {
    enabled = var.enable_point_in_time_recovery
  }

  # Server-side encryption
  server_side_encryption {
    enabled     = true
    kms_key_arn = var.kms_key_arn
  }

  tags = merge(var.tags, {
    Name = "${var.name_prefix}-sessions"
  })
}

# ============================================================================
# Bulk Jobs Table - Large-scale Import/Export State Management
# ============================================================================

resource "aws_dynamodb_table" "bulk_jobs" {
  name         = "${var.name_prefix}-bulk-jobs"
  billing_mode = var.jobs_table_billing_mode

  read_capacity  = var.jobs_table_billing_mode == "PROVISIONED" ? var.jobs_table_read_capacity : null
  write_capacity = var.jobs_table_billing_mode == "PROVISIONED" ? var.jobs_table_write_capacity : null

  # Primary key
  hash_key  = "pk"          # tenant_id
  range_key = "sk"          # bulk_job_id

  attribute {
    name = "pk"
    type = "S"
  }

  attribute {
    name = "sk"
    type = "S"
  }

  attribute {
    name = "state"
    type = "S"
  }

  attribute {
    name = "operation"
    type = "S"
  }

  attribute {
    name = "created_at"
    type = "S"
  }

  # GSI1: Query by state
  global_secondary_index {
    name            = "gsi1-state"
    hash_key        = "pk"
    range_key       = "state"
    projection_type = "ALL"

    read_capacity  = var.jobs_table_billing_mode == "PROVISIONED" ? var.jobs_table_read_capacity : null
    write_capacity = var.jobs_table_billing_mode == "PROVISIONED" ? var.jobs_table_write_capacity : null
  }

  # GSI2: Query by operation type
  global_secondary_index {
    name            = "gsi2-operation"
    hash_key        = "pk"
    range_key       = "operation"
    projection_type = "ALL"

    read_capacity  = var.jobs_table_billing_mode == "PROVISIONED" ? var.jobs_table_read_capacity : null
    write_capacity = var.jobs_table_billing_mode == "PROVISIONED" ? var.jobs_table_write_capacity : null
  }

  # GSI3: Query by creation time
  global_secondary_index {
    name            = "gsi3-created"
    hash_key        = "pk"
    range_key       = "created_at"
    projection_type = "ALL"

    read_capacity  = var.jobs_table_billing_mode == "PROVISIONED" ? var.jobs_table_read_capacity : null
    write_capacity = var.jobs_table_billing_mode == "PROVISIONED" ? var.jobs_table_write_capacity : null
  }

  # TTL configuration
  ttl {
    attribute_name = "ttl"
    enabled        = true
  }

  # Point-in-time recovery
  point_in_time_recovery {
    enabled = var.enable_point_in_time_recovery
  }

  # Server-side encryption
  server_side_encryption {
    enabled     = true
    kms_key_arn = var.kms_key_arn
  }

  tags = merge(var.tags, {
    Name = "${var.name_prefix}-bulk-jobs"
  })
}
