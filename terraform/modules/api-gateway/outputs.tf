# =============================================================================
# API Gateway Module Outputs
# =============================================================================

output "rest_api_id" {
  description = "ID of the REST API"
  value       = aws_api_gateway_rest_api.main.id
}

output "rest_api_arn" {
  description = "ARN of the REST API"
  value       = aws_api_gateway_rest_api.main.arn
}

output "execution_arn" {
  description = "Execution ARN of the REST API"
  value       = aws_api_gateway_rest_api.main.execution_arn
}

output "stage_name" {
  description = "Name of the deployment stage"
  value       = aws_api_gateway_stage.main.stage_name
}

output "invoke_url" {
  description = "Invoke URL of the API"
  value       = aws_api_gateway_stage.main.invoke_url
}

output "api_endpoint" {
  description = "Full API endpoint URL"
  value       = "${aws_api_gateway_stage.main.invoke_url}/v1"
}

output "custom_domain_url" {
  description = "Custom domain URL (if configured)"
  value       = var.custom_domain_name != null ? "https://${var.custom_domain_name}/${var.base_path}" : null
}

output "domain_name_regional_domain" {
  description = "Regional domain name for custom domain"
  value       = var.custom_domain_name != null ? aws_api_gateway_domain_name.main[0].regional_domain_name : null
}

output "domain_name_regional_zone_id" {
  description = "Regional zone ID for custom domain"
  value       = var.custom_domain_name != null ? aws_api_gateway_domain_name.main[0].regional_zone_id : null
}
