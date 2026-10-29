#!/usr/bin/env python3
"""Verify StackSet state, optionally checking IAM in every deployed account."""
import argparse
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def run_json(args, env=None):
    result = subprocess.run(args, env=env, text=True, capture_output=True, check=True)
    return json.loads(result.stdout)


def aws(*args, env=None, profile=None):
    command = ["aws", *args, "--output", "json", "--no-cli-pager"]
    if profile:
        command += ["--profile", profile]
    return run_json(command, env)


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--organization-profile", help="Profile that can assume member OrganizationAccountAccessRole")
    parser.add_argument("--member-profile", action="append", default=[], metavar="ACCOUNT=PROFILE")
    args = parser.parse_args()
    profiles = dict(item.split("=", 1) for item in args.member_profile)
    outputs = run_json(["terraform", f"-chdir={ROOT}", "output", "-json"])
    name = outputs["stack_set_id"]["value"]
    region = outputs["stack_set_arn"]["value"].split(":")[3]
    role_name = outputs["role_name"]["value"]
    management = outputs["trusted_management_account_id"]["value"]
    identity = aws("sts", "get-caller-identity")
    require(identity["Account"] == management, "Select the configured delegated administrator with AWS_PROFILE")
    common = ["--stack-set-name", name, "--region", region, "--call-as", "DELEGATED_ADMIN"]
    stackset = aws("cloudformation", "describe-stack-set", *common)["StackSet"]
    require(stackset["Status"] == "ACTIVE", "StackSet is not ACTIVE")
    require(stackset["PermissionModel"] == "SERVICE_MANAGED", "Unexpected permission model")
    require(stackset.get("AutoDeployment", {}).get("Enabled"), "Automatic account deployment is disabled")
    state = run_json(["terraform", f"-chdir={ROOT}", "show", "-json"])
    resource = next(r for r in state["values"]["root_module"]["resources"]
                    if r["address"] == "aws_cloudformation_stack_set.crossplane_role")
    require(stackset["TemplateBody"] == resource["values"]["template_body"], "Live template differs from Terraform state")
    instances = aws("cloudformation", "list-stack-instances", *common)["Summaries"]
    require(instances, "No deployed StackSet instances")
    for instance in instances:
        require(instance["Status"] == "CURRENT" and
                instance.get("StackInstanceStatus", {}).get("DetailedStatus") == "SUCCEEDED",
                f"Instance not ready: {instance['Account']} {instance['Region']}")
    print(f"StackSet {name}: ACTIVE; {len(instances)} instances CURRENT/SUCCEEDED")
    if not profiles and not args.organization_profile:
        print("CloudFormation checks passed; member IAM was not checked. Supply member-access profiles for IAM verification.")
        return
    expected_trust = {
        "Version": "2012-10-17",
        "Statement": [{
            "Effect": "Allow",
            "Principal": {"AWS": f"arn:aws:iam::{management}:root"},
            "Action": ["sts:AssumeRole", "sts:TagSession"],
            "Condition": {"StringLike": {
                "aws:PrincipalArn": f"arn:aws:iam::{management}:role/infra-plane-*-crossplane-role"
            }},
        }],
    }
    for account in sorted({item["Account"] for item in instances}):
        profile = profiles.get(account)
        env = None
        if not profile:
            require(args.organization_profile, f"No read access configured for account {account}")
            credentials = aws("sts", "assume-role", profile=args.organization_profile,
                              *["--role-arn", f"arn:aws:iam::{account}:role/OrganizationAccountAccessRole",
                                "--role-session-name", "verify-crossplane-entry-role"])["Credentials"]
            env = dict(os.environ)
            for key in ("AWS_PROFILE", "AWS_DEFAULT_PROFILE"):
                env.pop(key, None)
            env.update(AWS_ACCESS_KEY_ID=credentials["AccessKeyId"],
                       AWS_SECRET_ACCESS_KEY=credentials["SecretAccessKey"],
                       AWS_SESSION_TOKEN=credentials["SessionToken"])
        role = aws("iam", "get-role", "--role-name", role_name, env=env, profile=profile)["Role"]
        require(role["Arn"] == f"arn:aws:iam::{account}:role/{role_name}", "Unexpected role identity")
        require(role["AssumeRolePolicyDocument"] == expected_trust, f"Trust differs in {account}")
        policies = aws("iam", "list-attached-role-policies", "--role-name", role_name,
                       env=env, profile=profile)["AttachedPolicies"]
        require({p["PolicyArn"] for p in policies} == {"arn:aws:iam::aws:policy/AdministratorAccess"},
                f"Attached policies differ in {account}")
        require(not role.get("PermissionsBoundary"), f"Unexpected permissions boundary in {account}")
        inline = aws("iam", "list-role-policies", "--role-name", role_name, env=env, profile=profile)
        require(not inline["PolicyNames"], f"Unexpected inline policies in {account}")
        print(f"{account}: {role_name}; role ID {role['RoleId']}; child-only trust and AdministratorAccess verified")


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as error:
        raise SystemExit(error.stderr.strip()) from None
    except (RuntimeError, KeyError, ValueError) as error:
        raise SystemExit(str(error)) from None
