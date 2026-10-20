import { App, Aspects } from 'aws-cdk-lib';
import { AwsSolutionsChecks } from 'cdk-nag';
import { DataStack, ApplicationStack } from '../lib/stacks';

const app = new App();
const env = { account: process.env.CDK_DEFAULT_ACCOUNT, region: 'ap-south-1' };
const data = new DataStack(app, 'FinOpsData', {env, terminationProtection: true});
new ApplicationStack(app, 'FinOpsApplication', {env, data, terminationProtection: true});
Aspects.of(app).add(new AwsSolutionsChecks({verbose: true}));
