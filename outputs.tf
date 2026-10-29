output "stack_set_id" {
  description = "CloudFormation StackSet ID"
  value       = aws_cloudformation_stack_set.crossplane_role.id
}

output "stack_set_arn" {
  description = "CloudFormation StackSet ARN"
  value       = aws_cloudformation_stack_set.crossplane_role.arn
}

output "role_name" {
  description = "IAM role name deployed to member accounts"
  value       = var.crossplane_role_name
}

output "deployment_targets" {
  description = "Organizational units where the role is deployed"
  value       = var.target_organizational_unit_ids
}

output "trusted_management_account_id" {
  description = "Account whose child Crossplane roles may assume the member role"
  value       = var.management_account_id
}
