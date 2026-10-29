variable "aws_region" {
  description = "AWS region for StackSet management"
  type        = string
  default     = "us-west-2"
}

variable "stack_set_name" {
  description = "Name of the CloudFormation StackSet"
  type        = string
  default     = "crossplane-provider-roles"
}

variable "crossplane_role_name" {
  description = "IAM role name to create in member accounts"
  type        = string
  default     = "crossplane-provider-aws"
}

variable "management_account_id" {
  description = "AWS account ID where Crossplane management cluster runs"
  type        = string
}

variable "target_organizational_unit_ids" {
  description = "List of AWS Organization OU IDs to deploy the role to"
  type        = list(string)
}
