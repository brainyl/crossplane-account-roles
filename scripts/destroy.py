#!/usr/bin/env python3
"""Plan, destroy and verify the account-role StackSet using its saved state."""
import argparse
import json
import os
from pathlib import Path
import subprocess

from verify import ROOT, aws, require, run_json

PRIVATE = ROOT / '.local'
PLAN = PRIVATE / 'destroy.tfplan'
INVENTORY = PRIVATE / 'destroy-inventory.json'
ADDRESSES = {'aws_cloudformation_stack_set.crossplane_role',
             'aws_cloudformation_stack_set_instance.crossplane_role'}


def review():
    plan = run_json(['terraform', f'-chdir={ROOT}', 'show', '-json', str(PLAN)])
    changes = [x for x in plan.get('resource_changes', []) if x['change']['actions'] != ['no-op']]
    require({x['address'] for x in changes} == ADDRESSES, 'Unexpected StackSet destroy scope')
    require(all(x['change']['actions'] == ['delete'] for x in changes), 'Destroy plan contains non-delete actions')
    instance = next(x for x in changes if x['address'].startswith('aws_cloudformation_stack_set_instance.'))
    require(instance['change']['before']['retain_stack'] is False, 'Refusing to orphan member stacks')
    print('Reviewed: delete StackSet instances (retain_stack=false), then StackSet; no creates/updates.')


def verify(args, inventory):
    require(not subprocess.check_output(['terraform', f'-chdir={ROOT}', 'state', 'list'], text=True).strip(),
            'StackSet Terraform state is not empty')
    result = subprocess.run(['aws', 'cloudformation', 'describe-stack-set', '--stack-set-name', inventory['name'],
                             '--region', inventory['region'], '--call-as', 'DELEGATED_ADMIN', '--output', 'json'],
                            text=True, capture_output=True)
    if result.returncode:
        require('StackSetNotFoundException' in result.stderr, result.stderr)
    else:
        require(json.loads(result.stdout)['StackSet']['Status'] == 'DELETED', 'StackSet still exists')
    profiles = dict(x.split('=', 1) for x in args.member_profile)
    for item in inventory['instances']:
        account = item['Account']
        profile = profiles.get(account)
        env = None
        if not profile:
            require(args.organization_profile, f'Provide IAM verification access for {account}')
            credentials = aws('sts', 'assume-role', '--role-arn', f'arn:aws:iam::{account}:role/OrganizationAccountAccessRole',
                              '--role-session-name', 'verify-stackset-deletion', profile=args.organization_profile)['Credentials']
            env = {k: v for k, v in os.environ.items() if k not in ('AWS_PROFILE', 'AWS_DEFAULT_PROFILE')}
            env.update(AWS_ACCESS_KEY_ID=credentials['AccessKeyId'], AWS_SECRET_ACCESS_KEY=credentials['SecretAccessKey'],
                       AWS_SESSION_TOKEN=credentials['SessionToken'])
        require(aws('sts', 'get-caller-identity', env=env, profile=profile)['Account'] == account, 'Wrong member identity')
        command = ['aws', 'iam', 'get-role', '--role-name', inventory['roleName'], '--output', 'json']
        if profile:
            command += ['--profile', profile]
        result = subprocess.run(command, env=env, text=True, capture_output=True)
        require(result.returncode != 0 and 'NoSuchEntity' in result.stderr, f'Role deletion not verified in {account}')
        print(f'{account}: {inventory["roleName"]} absent')
    print('Verified: StackSet deleted, member roles absent, Terraform state empty.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage', choices=['plan', 'apply', 'verify'])
    parser.add_argument('--organization-profile')
    parser.add_argument('--member-profile', action='append', default=[], metavar='ACCOUNT=PROFILE')
    args = parser.parse_args()
    os.umask(0o077)
    PRIVATE.mkdir(exist_ok=True)
    if args.stage == 'plan':
        outputs = run_json(['terraform', f'-chdir={ROOT}', 'output', '-json'])
        inventory = {'name': outputs['stack_set_id']['value'], 'region': outputs['stack_set_arn']['value'].split(':')[3],
                     'account': outputs['trusted_management_account_id']['value'], 'roleName': outputs['role_name']['value']}
        require(aws('sts', 'get-caller-identity')['Account'] == inventory['account'], 'Wrong delegated administrator')
        inventory['instances'] = aws('cloudformation', 'list-stack-instances', '--stack-set-name', inventory['name'],
                                     '--region', inventory['region'], '--call-as', 'DELEGATED_ADMIN')['Summaries']
        INVENTORY.write_text(json.dumps(inventory, indent=2))
        subprocess.run(['terraform', f'-chdir={ROOT}', 'plan', '-destroy', '-input=false', f'-out={PLAN}'], check=True)
        review()
        return
    inventory = json.loads(INVENTORY.read_text())
    require(aws('sts', 'get-caller-identity')['Account'] == inventory['account'], 'Wrong delegated administrator')
    if args.stage == 'apply':
        review()
        subprocess.run(['terraform', f'-chdir={ROOT}', 'apply', '-input=false', str(PLAN)], check=True)
    verify(args, inventory)


if __name__ == '__main__':
    main()
