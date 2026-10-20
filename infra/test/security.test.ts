import { test } from 'node:test';
import assert from 'node:assert/strict';
import { App } from 'aws-cdk-lib';
import { Template, Match } from 'aws-cdk-lib/assertions';
import { DataStack, ApplicationStack } from '../lib/stacks';

const app = new App();
const env = {account:'123456789012',region:'ap-south-1'};
const data = new DataStack(app,'FinOpsData',{env});
const application = new ApplicationStack(app,'FinOpsApplication',{env,data});
const persistent = Template.fromStack(data);
const runtime = Template.fromStack(application);

test('operational data is encrypted, retained, protected and recoverable',()=>{
  persistent.hasResourceProperties('AWS::DynamoDB::Table',{
    BillingMode:'PAY_PER_REQUEST',DeletionProtectionEnabled:true,
    PointInTimeRecoverySpecification:{PointInTimeRecoveryEnabled:true},
    SSESpecification:Match.objectLike({SSEEnabled:true,SSEType:'KMS'}),
    StreamSpecification:{StreamViewType:'NEW_IMAGE'}
  });
  persistent.hasResource('AWS::DynamoDB::Table',{DeletionPolicy:'Retain',UpdateReplacePolicy:'Retain'});
  persistent.resourceCountIs('AWS::RDS::DBCluster',0);
  persistent.resourceCountIs('AWS::RDS::DBProxy',0);
});
test('Cognito keeps MFA optional and requires verified email',()=>{
  persistent.hasResourceProperties('AWS::Cognito::UserPool',{MfaConfiguration:'OPTIONAL',UserPoolTier:'PLUS',
    AutoVerifiedAttributes:['email'],EnabledMfas:['SOFTWARE_TOKEN_MFA']});
});
test('durable work uses a stream outbox, Standard workflow and failure queue',()=>{
  runtime.hasResourceProperties('AWS::StepFunctions::StateMachine',{StateMachineType:'STANDARD',
    LoggingConfiguration:Match.objectLike({IncludeExecutionData:false,Level:'ALL'})});
  runtime.hasResourceProperties('AWS::Lambda::EventSourceMapping',{FunctionResponseTypes:['ReportBatchItemFailures'],
    MaximumRetryAttempts:5,StartingPosition:'TRIM_HORIZON',FilterCriteria:Match.anyValue()});
  runtime.resourceCountIs('AWS::SQS::Queue',1);
  runtime.hasResourceProperties('AWS::Glue::Table',{TableInput:Match.objectLike({Parameters:Match.objectLike({
    'projection.enabled':'true','projection.tenant.type':'injected','projection.connection.type':'injected','projection.snapshot.type':'injected'
  }),PartitionKeys:[{Name:'tenant',Type:'string'},{Name:'connection',Type:'string'},{Name:'snapshot',Type:'string'}]})});
});
test('business API never logs bodies and Bedrock stays disabled initially',()=>{
  runtime.hasResourceProperties('AWS::CloudFront::Distribution',{DistributionConfig:Match.objectLike({Logging:Match.absent()})});
  runtime.hasResourceProperties('AWS::ApiGateway::Stage',{MethodSettings:Match.arrayWith([Match.objectLike({DataTraceEnabled:false})])});
  runtime.hasResourceProperties('AWS::Lambda::Function',{Handler:'services.api.lambda_handler.handler',
    Environment:{Variables:Match.objectLike({FINOPS_STORE:'dynamodb',FINOPS_BEDROCK_ENABLED:'false'})}});
  const serialized=JSON.stringify(runtime.toJSON());
  assert(!serialized.includes('AWS_SECRET_ACCESS_KEY'));
  assert(!serialized.includes('bedrock:InvokeModel'));
  const policies=runtime.findResources('AWS::IAM::Policy');
  const apiPolicy=Object.entries(policies).find(([key])=>key.startsWith('ApiServiceRole'));
  assert(apiPolicy);
  assert(!JSON.stringify(apiPolicy[1]).includes('s3:DeleteObject'));
});
test('CloudTrail can use its KMS key only for the declared trail',()=>{
  persistent.hasResourceProperties('AWS::KMS::Key',{KeyPolicy:Match.objectLike({Statement:Match.arrayWith([
    Match.objectLike({Principal:{Service:'cloudtrail.amazonaws.com'},Condition:{StringEquals:{'aws:SourceArn':Match.objectLike({'Fn::Join':['',Match.arrayWith([':cloudtrail:ap-south-1:123456789012:trail/finops-management'])]})}}})
  ])})});
  persistent.hasResourceProperties('AWS::CloudTrail::Trail',{EnableLogFileValidation:true,IsMultiRegionTrail:true,TrailName:'finops-management'});
});
