# Crossplane account roles

Deploys `crossplane-provider-aws` IAM roles across selected AWS Organizations OUs using a CloudFormation StackSet. Each role grants AdministratorAccess and trusts child Crossplane roles matching `infra-plane-*-crossplane-role` in the platform account.

Terraform manages the StackSet; CloudFormation manages the account roles. Accounts added to targeted OUs receive the role automatically. Removing an account from those OUs removes its role.

## Account responsibilities

| Account | Responsibility |
|---|---|
| Organization management | Enables StackSets trusted access and registers a delegated administrator. |
| Platform | Hosts infra management clusters and runs Terraform as the delegated administrator. |
| Workload | Receives the IAM role that Crossplane assumes to provision resources. |

The platform account manages the organization's StackSet using `DELEGATED_ADMIN` permissions. Crossplane uses the deployed roles; it does not manage the StackSet.

> [!NOTE]
> **This repository creates roles, not AWS accounts or networks.** Create the Organization, accounts/OUs and SSO access before running it. `management_account_id` means the platform/delegated-administrator account, not the Organization management account. IAM delegation does not connect VPCs.

## Setup

Requires AWS CLI, Terraform 1.x (`~> 1.5`), Python 3, and AWS access to the accounts above. Profile names below are examples; replace placeholders with your own values.

Once per organization, enable trusted access and register the delegated administrator from the organization management account:

```bash
aws cloudformation activate-organizations-access --profile organization-admin --region us-west-2
aws organizations register-delegated-administrator \
  --profile organization-admin --account-id '<PLATFORM_ACCOUNT_ID>' \
  --service-principal member.org.stacksets.cloudformation.amazonaws.com
```

Copy `terraform.tfvars.example` to `terraform.tfvars`. Set `management_account_id` to the platform account ID and supply your target OU IDs and region. For an existing deployment, use its saved Terraform state and inputs.

## Deploy

Run from this directory:

```bash
aws sso login --profile platform-admin
export AWS_PROFILE=platform-admin
export EXPECTED_AWS_ACCOUNT_ID='<PLATFORM_ACCOUNT_ID>'
./scripts/deploy.sh plan
# Review the plan before applying.
./scripts/deploy.sh apply
```

Repeat SSO login when the session expires. The script checks the account, applies the saved plan, and verifies every StackSet instance. Change `templates/crossplane-role.yaml` to update role permissions or trust.

## Verify

```bash
AWS_PROFILE=platform-admin python3 scripts/verify.py
```

Requires an active StackSet and CURRENT/SUCCEEDED instances. For direct IAM checks, supply your own `--organization-profile` and `--member-profile ACCOUNT=PROFILE` values; see `python3 scripts/verify.py --help`.

Verify the account role before enabling workload environments. Keep state, private inputs, and plans out of Git; commit the provider lock file.

## Tear down

Delete dependent environments first; removing these roles removes Crossplane's access to their accounts. Keep the saved Terraform state and original region until destruction finishes.

```bash
export AWS_PROFILE=platform-admin
python3 scripts/destroy.py plan
# Review: delete member stacks (retain_stack=false), then the StackSet.
python3 scripts/destroy.py apply --organization-profile organization-admin \
  --member-profile '<PLATFORM_ACCOUNT_ID>=platform-admin'
```

Supply additional `--member-profile ACCOUNT=PROFILE` arguments for accounts where the organization profile cannot assume `OrganizationAccountAccessRole`. Verification checks the deleted StackSet, empty Terraform state and missing IAM role in every recorded account. Repeat verification with `scripts/destroy.py verify` and the same profile arguments if interrupted. Private inventory and plan remain in `.local/`.

The class StackSet targets Oregon (`us-west-2`). IAM roles are global: install their owning StackSet in one region only. Environment teardown does not remove organization trusted access or delegated-administrator registration.

To rebuild after teardown, reuse the saved inputs and empty Terraform state, renew SSO if expired, then repeat **Deploy** and **Verify**. Trusted access/delegation need setup only when absent or intentionally changed; no playbook checkout is required.
