# =============================================================================
# Monitoring Module
# CloudWatch Dashboards, Alarms, and Observability for Redshift Spectra
# =============================================================================
# Note: Lambda log groups are managed by the Lambda module itself.
# This module manages API Gateway log groups, dashboards, and alarms.
# =============================================================================

# -----------------------------------------------------------------------------
# CloudWatch Log Groups (non-Lambda)
# -----------------------------------------------------------------------------
resource "aws_cloudwatch_log_group" "api_gateway" {
  name              = "/aws/api-gateway/${var.project_name}-${var.environment}"
  retention_in_days = var.log_retention_days

  tags = merge(var.tags, {
    Component = "api-gateway"
  })
}

# -----------------------------------------------------------------------------
# CloudWatch Dashboard
# -----------------------------------------------------------------------------
resource "aws_cloudwatch_dashboard" "main" {
  dashboard_name = "${var.project_name}-${var.environment}"

  dashboard_body = jsonencode({
    widgets = [
      # API Gateway Metrics Row
      {
        type   = "text"
        x      = 0
        y      = 0
        width  = 24
        height = 1
        properties = {
          markdown = "# API Gateway Metrics"
        }
      },
      {
        type   = "metric"
        x      = 0
        y      = 1
        width  = 8
        height = 6
        properties = {
          title  = "API Requests"
          region = var.aws_region
          metrics = [
            ["AWS/ApiGateway", "Count", "ApiName", "${var.project_name}-${var.environment}-api", { stat = "Sum", period = 60 }]
          ]
          view = "timeSeries"
        }
      },
      {
        type   = "metric"
        x      = 8
        y      = 1
        width  = 8
        height = 6
        properties = {
          title  = "API Latency (p50, p90, p99)"
          region = var.aws_region
          metrics = [
            ["AWS/ApiGateway", "Latency", "ApiName", "${var.project_name}-${var.environment}-api", { stat = "p50", period = 60 }],
            ["...", { stat = "p90", period = 60 }],
            ["...", { stat = "p99", period = 60 }]
          ]
          view = "timeSeries"
        }
      },
      {
        type   = "metric"
        x      = 16
        y      = 1
        width  = 8
        height = 6
        properties = {
          title  = "API Errors (4xx, 5xx)"
          region = var.aws_region
          metrics = [
            ["AWS/ApiGateway", "4XXError", "ApiName", "${var.project_name}-${var.environment}-api", { stat = "Sum", period = 60, color = "#ff7f0e" }],
            [".", "5XXError", ".", ".", { stat = "Sum", period = 60, color = "#d62728" }]
          ]
          view = "timeSeries"
        }
      },

      # Lambda Metrics Row
      {
        type   = "text"
        x      = 0
        y      = 7
        width  = 24
        height = 1
        properties = {
          markdown = "# Lambda Function Metrics"
        }
      },
      {
        type   = "metric"
        x      = 0
        y      = 8
        width  = 6
        height = 6
        properties = {
          title  = "Query Lambda - Invocations & Errors"
          region = var.aws_region
          metrics = [
            ["AWS/Lambda", "Invocations", "FunctionName", "${var.project_name}-${var.environment}-query", { stat = "Sum", period = 60 }],
            [".", "Errors", ".", ".", { stat = "Sum", period = 60, color = "#d62728" }]
          ]
          view = "timeSeries"
        }
      },
      {
        type   = "metric"
        x      = 6
        y      = 8
        width  = 6
        height = 6
        properties = {
          title  = "Status Lambda - Invocations & Errors"
          region = var.aws_region
          metrics = [
            ["AWS/Lambda", "Invocations", "FunctionName", "${var.project_name}-${var.environment}-status", { stat = "Sum", period = 60 }],
            [".", "Errors", ".", ".", { stat = "Sum", period = 60, color = "#d62728" }]
          ]
          view = "timeSeries"
        }
      },
      {
        type   = "metric"
        x      = 12
        y      = 8
        width  = 6
        height = 6
        properties = {
          title  = "Result Lambda - Invocations & Errors"
          region = var.aws_region
          metrics = [
            ["AWS/Lambda", "Invocations", "FunctionName", "${var.project_name}-${var.environment}-result", { stat = "Sum", period = 60 }],
            [".", "Errors", ".", ".", { stat = "Sum", period = 60, color = "#d62728" }]
          ]
          view = "timeSeries"
        }
      },
      {
        type   = "metric"
        x      = 18
        y      = 8
        width  = 6
        height = 6
        properties = {
          title  = "Bulk Lambda - Invocations & Errors"
          region = var.aws_region
          metrics = [
            ["AWS/Lambda", "Invocations", "FunctionName", "${var.project_name}-${var.environment}-bulk", { stat = "Sum", period = 60 }],
            [".", "Errors", ".", ".", { stat = "Sum", period = 60, color = "#d62728" }]
          ]
          view = "timeSeries"
        }
      },
      {
        type   = "metric"
        x      = 0
        y      = 14
        width  = 12
        height = 6
        properties = {
          title  = "Lambda Duration (ms)"
          region = var.aws_region
          metrics = [
            ["AWS/Lambda", "Duration", "FunctionName", "${var.project_name}-${var.environment}-query", { stat = "Average", period = 60 }],
            [".", ".", ".", "${var.project_name}-${var.environment}-status", { stat = "Average", period = 60 }],
            [".", ".", ".", "${var.project_name}-${var.environment}-result", { stat = "Average", period = 60 }],
            [".", ".", ".", "${var.project_name}-${var.environment}-bulk", { stat = "Average", period = 60 }]
          ]
          view = "timeSeries"
        }
      },
      {
        type   = "metric"
        x      = 12
        y      = 14
        width  = 12
        height = 6
        properties = {
          title  = "Lambda Concurrent Executions"
          region = var.aws_region
          metrics = [
            ["AWS/Lambda", "ConcurrentExecutions", "FunctionName", "${var.project_name}-${var.environment}-query", { stat = "Maximum", period = 60 }],
            [".", ".", ".", "${var.project_name}-${var.environment}-bulk", { stat = "Maximum", period = 60 }]
          ]
          view = "timeSeries"
        }
      },

      # DynamoDB Metrics Row
      {
        type   = "text"
        x      = 0
        y      = 20
        width  = 24
        height = 1
        properties = {
          markdown = "# DynamoDB Metrics"
        }
      },
      {
        type   = "metric"
        x      = 0
        y      = 21
        width  = 8
        height = 6
        properties = {
          title  = "Jobs Table - Read/Write Capacity"
          region = var.aws_region
          metrics = [
            ["AWS/DynamoDB", "ConsumedReadCapacityUnits", "TableName", "${var.project_name}-${var.environment}-jobs", { stat = "Sum", period = 60 }],
            [".", "ConsumedWriteCapacityUnits", ".", ".", { stat = "Sum", period = 60 }]
          ]
          view = "timeSeries"
        }
      },
      {
        type   = "metric"
        x      = 8
        y      = 21
        width  = 8
        height = 6
        properties = {
          title  = "Bulk Jobs Table - Read/Write Capacity"
          region = var.aws_region
          metrics = [
            ["AWS/DynamoDB", "ConsumedReadCapacityUnits", "TableName", "${var.project_name}-${var.environment}-bulk-jobs", { stat = "Sum", period = 60 }],
            [".", "ConsumedWriteCapacityUnits", ".", ".", { stat = "Sum", period = 60 }]
          ]
          view = "timeSeries"
        }
      },
      {
        type   = "metric"
        x      = 16
        y      = 21
        width  = 8
        height = 6
        properties = {
          title  = "DynamoDB Throttled Requests"
          region = var.aws_region
          metrics = [
            ["AWS/DynamoDB", "ThrottledRequests", "TableName", "${var.project_name}-${var.environment}-jobs", { stat = "Sum", period = 60 }],
            [".", ".", ".", "${var.project_name}-${var.environment}-bulk-jobs", { stat = "Sum", period = 60 }]
          ]
          view = "timeSeries"
        }
      },

      # Custom Metrics Row
      {
        type   = "text"
        x      = 0
        y      = 27
        width  = 24
        height = 1
        properties = {
          markdown = "# Application Metrics"
        }
      },
      {
        type   = "metric"
        x      = 0
        y      = 28
        width  = 8
        height = 6
        properties = {
          title  = "Query Jobs by Status"
          region = var.aws_region
          metrics = [
            ["${var.project_name}", "JobsCreated", "Environment", var.environment, { stat = "Sum", period = 300 }],
            [".", "JobsCompleted", ".", ".", { stat = "Sum", period = 300 }],
            [".", "JobsFailed", ".", ".", { stat = "Sum", period = 300, color = "#d62728" }]
          ]
          view = "timeSeries"
        }
      },
      {
        type   = "metric"
        x      = 8
        y      = 28
        width  = 8
        height = 6
        properties = {
          title  = "Bulk Jobs by Operation"
          region = var.aws_region
          metrics = [
            ["${var.project_name}", "BulkExportJobs", "Environment", var.environment, { stat = "Sum", period = 300 }],
            [".", "BulkImportJobs", ".", ".", { stat = "Sum", period = 300 }]
          ]
          view = "timeSeries"
        }
      },
      {
        type   = "metric"
        x      = 16
        y      = 28
        width  = 8
        height = 6
        properties = {
          title  = "Data Transfer Volume"
          region = var.aws_region
          metrics = [
            ["${var.project_name}", "DataExportedBytes", "Environment", var.environment, { stat = "Sum", period = 300 }],
            [".", "DataImportedBytes", ".", ".", { stat = "Sum", period = 300 }]
          ]
          view = "timeSeries"
        }
      }
    ]
  })
}

# -----------------------------------------------------------------------------
# CloudWatch Alarms
# -----------------------------------------------------------------------------

# API Gateway 5xx Error Rate Alarm
resource "aws_cloudwatch_metric_alarm" "api_5xx_errors" {
  alarm_name          = "${var.project_name}-${var.environment}-api-5xx-errors"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "5XXError"
  namespace           = "AWS/ApiGateway"
  period              = 60
  statistic           = "Sum"
  threshold           = var.api_error_threshold
  alarm_description   = "API Gateway 5xx error rate exceeded threshold"
  treat_missing_data  = "notBreaching"

  dimensions = {
    ApiName = "${var.project_name}-${var.environment}-api"
  }

  alarm_actions = var.alarm_actions
  ok_actions    = var.ok_actions

  tags = var.tags
}

# API Gateway Latency Alarm
resource "aws_cloudwatch_metric_alarm" "api_latency" {
  alarm_name          = "${var.project_name}-${var.environment}-api-latency"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 3
  metric_name         = "Latency"
  namespace           = "AWS/ApiGateway"
  period              = 60
  extended_statistic  = "p99"
  threshold           = var.api_latency_threshold_ms
  alarm_description   = "API Gateway p99 latency exceeded threshold"
  treat_missing_data  = "notBreaching"

  dimensions = {
    ApiName = "${var.project_name}-${var.environment}-api"
  }

  alarm_actions = var.alarm_actions
  ok_actions    = var.ok_actions

  tags = var.tags
}

# Lambda Error Rate Alarms
resource "aws_cloudwatch_metric_alarm" "lambda_errors" {
  for_each = var.lambda_function_names != null ? var.lambda_function_names : {}

  alarm_name          = "${var.project_name}-${var.environment}-${each.key}-lambda-errors"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "Errors"
  namespace           = "AWS/Lambda"
  period              = 60
  statistic           = "Sum"
  threshold           = var.lambda_error_threshold
  alarm_description   = "${each.key} Lambda error rate exceeded threshold"
  treat_missing_data  = "notBreaching"

  dimensions = {
    FunctionName = each.value
  }

  alarm_actions = var.alarm_actions
  ok_actions    = var.ok_actions

  tags = var.tags
}

# Lambda Duration Alarms (API and Worker only)
resource "aws_cloudwatch_metric_alarm" "lambda_duration" {
  for_each = var.lambda_function_names != null ? {
    api    = var.lambda_function_names.api
    worker = var.lambda_function_names.worker
  } : {}

  alarm_name          = "${var.project_name}-${var.environment}-${each.key}-lambda-duration"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 3
  metric_name         = "Duration"
  namespace           = "AWS/Lambda"
  period              = 60
  extended_statistic  = "p95"
  threshold           = var.lambda_duration_threshold_ms
  alarm_description   = "${each.key} Lambda p95 duration exceeded threshold"
  treat_missing_data  = "notBreaching"

  dimensions = {
    FunctionName = each.value
  }

  alarm_actions = var.alarm_actions
  ok_actions    = var.ok_actions

  tags = var.tags
}

# DynamoDB Throttling Alarm
resource "aws_cloudwatch_metric_alarm" "dynamodb_throttling" {
  for_each = toset(["jobs", "bulk-jobs"])

  alarm_name          = "${var.project_name}-${var.environment}-${each.key}-throttling"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "ThrottledRequests"
  namespace           = "AWS/DynamoDB"
  period              = 60
  statistic           = "Sum"
  threshold           = 0
  alarm_description   = "${each.key} DynamoDB table experiencing throttling"
  treat_missing_data  = "notBreaching"

  dimensions = {
    TableName = "${var.project_name}-${var.environment}-${each.key}"
  }

  alarm_actions = var.alarm_actions
  ok_actions    = var.ok_actions

  tags = var.tags
}

# -----------------------------------------------------------------------------
# SNS Topic for Alerts
# -----------------------------------------------------------------------------
resource "aws_sns_topic" "alerts" {
  count = var.create_sns_topic ? 1 : 0
  name  = "${var.project_name}-${var.environment}-alerts"

  tags = var.tags
}

resource "aws_sns_topic_subscription" "email" {
  count     = var.create_sns_topic && var.alert_email != null ? 1 : 0
  topic_arn = aws_sns_topic.alerts[0].arn
  protocol  = "email"
  endpoint  = var.alert_email
}

# -----------------------------------------------------------------------------
# X-Ray Tracing
# -----------------------------------------------------------------------------
resource "aws_xray_sampling_rule" "main" {
  count         = var.enable_xray_tracing ? 1 : 0
  rule_name     = "${var.project_name}-${var.environment}"
  priority      = 1000
  version       = 1
  reservoir_size = 5
  fixed_rate    = 0.05
  url_path      = "*"
  host          = "*"
  http_method   = "*"
  service_type  = "*"
  service_name  = "${var.project_name}-${var.environment}"
  resource_arn  = "*"

  tags = var.tags
}

# -----------------------------------------------------------------------------
# CloudWatch Insights Queries
# -----------------------------------------------------------------------------
resource "aws_cloudwatch_query_definition" "error_analysis" {
  count = var.lambda_log_group_names != null ? 1 : 0
  name  = "${var.project_name}/${var.environment}/Error Analysis"

  log_group_names = values(var.lambda_log_group_names)

  query_string = <<-EOF
    fields @timestamp, @message, @logStream
    | filter @message like /ERROR|Exception|error/
    | sort @timestamp desc
    | limit 100
  EOF
}

resource "aws_cloudwatch_query_definition" "slow_queries" {
  count = var.lambda_log_group_names != null ? 1 : 0
  name  = "${var.project_name}/${var.environment}/Slow Queries"

  log_group_names = [
    var.lambda_log_group_names.api,
    var.lambda_log_group_names.worker,
  ]

  query_string = <<-EOF
    fields @timestamp, @duration, @message
    | filter @type = "REPORT"
    | filter @duration > 10000
    | sort @duration desc
    | limit 50
  EOF
}

resource "aws_cloudwatch_query_definition" "tenant_activity" {
  count = var.lambda_log_group_names != null ? 1 : 0
  name  = "${var.project_name}/${var.environment}/Tenant Activity"

  log_group_names = [
    var.lambda_log_group_names.api,
    var.lambda_log_group_names.worker,
  ]

  query_string = <<-EOF
    fields @timestamp, tenant_id, operation, @message
    | filter ispresent(tenant_id)
    | stats count(*) as request_count by tenant_id, operation
    | sort request_count desc
  EOF
}
