terraform {
  required_version = "~> 1.5"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.28"
    }
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      ManagedBy = "Terraform"
      Purpose   = "Crossplane-Member-Roles"
    }
  }
}

# CloudFormation StackSet for Crossplane IAM role
resource "aws_cloudformation_stack_set" "crossplane_role" {
  name             = var.stack_set_name
  description      = "Deploys Crossplane provider IAM role to member accounts"
  permission_model = "SERVICE_MANAGED"
  call_as          = "DELEGATED_ADMIN"

  auto_deployment {
    enabled                          = true
    retain_stacks_on_account_removal = false
  }

  capabilities = ["CAPABILITY_NAMED_IAM"]

  template_body = templatefile("${path.module}/templates/crossplane-role.yaml", {
    role_name             = var.crossplane_role_name
    management_account_id = var.management_account_id
  })

  lifecycle {
    ignore_changes = [administration_role_arn]
  }
}

# Deploy to organizational units
resource "aws_cloudformation_stack_set_instance" "crossplane_role" {
  stack_set_name = aws_cloudformation_stack_set.crossplane_role.name
  call_as        = "DELEGATED_ADMIN"

  deployment_targets {
    organizational_unit_ids = var.target_organizational_unit_ids
  }

  operation_preferences {
    failure_tolerance_count = 0
    max_concurrent_count    = 10
    region_concurrency_type = "PARALLEL"
  }
}
