import * as cdk from 'aws-cdk-lib';
import { Construct } from 'constructs';
import { NagSuppressions } from 'cdk-nag';
import * as path from 'node:path';
import * as fs from 'node:fs';
import { aws_s3 as s3, aws_kms as kms, aws_dynamodb as ddb, aws_lambda as lambda, aws_logs as logs,
  aws_cloudfront as cf, aws_cloudfront_origins as origins, aws_apigateway as apigw,
  aws_cognito as cognito, aws_iam as iam, aws_s3_deployment as deployment, aws_ssm as ssm,
  aws_stepfunctions as sfn, aws_stepfunctions_tasks as tasks, aws_lambda_event_sources as sources,
  aws_sqs as sqs, aws_cloudwatch as cw, aws_wafv2 as waf, aws_glue as glue, aws_athena as athena,
  aws_cloudtrail as cloudtrail } from 'aws-cdk-lib';

export class DataStack extends cdk.Stack {
  readonly key: kms.Key;
  readonly table: ddb.Table;
  readonly dataBucket: s3.Bucket;
  readonly accessLogs: s3.Bucket;
  readonly pool: cognito.UserPool;
  constructor(scope: Construct, id: string, props: cdk.StackProps) {
    super(scope,id,props);
    this.key = new kms.Key(this,'EncryptionKey',{enableKeyRotation:true,removalPolicy:cdk.RemovalPolicy.RETAIN});
    this.accessLogs = new s3.Bucket(this,'AccessLogs',{encryption:s3.BucketEncryption.S3_MANAGED,
      blockPublicAccess:s3.BlockPublicAccess.BLOCK_ALL,enforceSSL:true,objectOwnership:s3.ObjectOwnership.OBJECT_WRITER,
      removalPolicy:cdk.RemovalPolicy.RETAIN,lifecycleRules:[{expiration:cdk.Duration.days(180)}]});
    // Keep the existing cross-stack export while the consumer removes legacy edge logging.
    // Removing an export before its deployed consumer updates would block CloudFormation.
    this.exportValue(this.accessLogs.bucketRegionalDomainName);
    this.dataBucket = new s3.Bucket(this,'Analytics',{encryption:s3.BucketEncryption.KMS,encryptionKey:this.key,bucketKeyEnabled:true,
      blockPublicAccess:s3.BlockPublicAccess.BLOCK_ALL,enforceSSL:true,versioned:true,
      serverAccessLogsBucket:this.accessLogs,serverAccessLogsPrefix:'analytics/',removalPolicy:cdk.RemovalPolicy.RETAIN});
    this.table = new ddb.Table(this,'OperationalData',{partitionKey:{name:'pk',type:ddb.AttributeType.STRING},sortKey:{name:'sk',type:ddb.AttributeType.STRING},
      billingMode:ddb.BillingMode.PAY_PER_REQUEST,encryption:ddb.TableEncryption.CUSTOMER_MANAGED,encryptionKey:this.key,
      pointInTimeRecoverySpecification:{pointInTimeRecoveryEnabled:true},deletionProtection:true,stream:ddb.StreamViewType.NEW_IMAGE,
      timeToLiveAttribute:'expires',removalPolicy:cdk.RemovalPolicy.RETAIN});
    this.pool = new cognito.UserPool(this,'Customers',{selfSignUpEnabled:true,signInAliases:{email:true},
      featurePlan:cognito.FeaturePlan.PLUS,standardThreatProtectionMode:cognito.StandardThreatProtectionMode.FULL_FUNCTION,
      autoVerify:{email:true},standardAttributes:{email:{required:true,mutable:true},fullname:{required:true,mutable:true}},
      mfa:cognito.Mfa.REQUIRED,mfaSecondFactor:{sms:false,otp:true},accountRecovery:cognito.AccountRecovery.EMAIL_ONLY,
      passwordPolicy:{minLength:12,requireDigits:true,requireLowercase:true,requireUppercase:true,requireSymbols:true},
      removalPolicy:cdk.RemovalPolicy.RETAIN});
    const trailArn = this.formatArn({service:'cloudtrail',resource:'trail',resourceName:'finops-management',arnFormat:cdk.ArnFormat.SLASH_RESOURCE_NAME});
    this.key.addToResourcePolicy(new iam.PolicyStatement({principals:[new iam.ServicePrincipal('cloudtrail.amazonaws.com')],
      actions:['kms:GenerateDataKey*','kms:DescribeKey','kms:Decrypt'],resources:['*'],conditions:{StringEquals:{'aws:SourceArn':trailArn}}}));
    const trail = new cloudtrail.Trail(this,'ManagementAudit',{trailName:'finops-management',bucket:this.dataBucket,s3KeyPrefix:'cloudtrail',encryptionKey:this.key,
      enableFileValidation:true,isMultiRegionTrail:true,includeGlobalServiceEvents:true});
    const policy = this.dataBucket.policy!.document;
    // Restrict CDK's CloudTrail service grants to this exact trail.
    const statements = policy.toJSON().Statement as {Principal?: {Service?:string};Condition?: Record<string,unknown>}[];
    for(const statement of statements) if(statement.Principal?.Service === 'cloudtrail.amazonaws.com') {
      statement.Condition = {...statement.Condition,StringEquals:{...((statement.Condition?.StringEquals ?? {}) as Record<string,unknown>),'aws:SourceArn':trailArn}};
    }
    const bucketPolicy = this.dataBucket.policy!.node.defaultChild as s3.CfnBucketPolicy;
    bucketPolicy.policyDocument = {...policy.toJSON(),Statement:statements};
    trail.applyRemovalPolicy(cdk.RemovalPolicy.RETAIN);
    NagSuppressions.addResourceSuppressions(this.accessLogs,[{id:'AwsSolutions-S1',reason:'Dedicated access-log destination. Self-logging would recursively generate log objects.'}]);
    new cdk.CfnOutput(this,'UserPoolId',{value:this.pool.userPoolId});
  }
}

interface ApplicationProps extends cdk.StackProps { readonly data: DataStack; }
export class ApplicationStack extends cdk.Stack {
  constructor(scope: Construct,id: string,props: ApplicationProps) {
    super(scope,id,props);
    const {data} = props;
    const webBucket = new s3.Bucket(this,'Frontend',{encryption:s3.BucketEncryption.S3_MANAGED,
      blockPublicAccess:s3.BlockPublicAccess.BLOCK_ALL,enforceSSL:true,serverAccessLogsBucket:data.accessLogs,
      serverAccessLogsPrefix:'web/',removalPolicy:cdk.RemovalPolicy.RETAIN});
    const assetPath = path.resolve(__dirname,'../../.cache/lambda');
    if(!fs.existsSync(path.join(assetPath,'services/api/main.py'))) throw new Error('Run scripts/package-lambda.ps1 before synthesis.');
    const code = lambda.Code.fromAsset(assetPath,{exclude:['**/__pycache__/**','**/*.pyc']});
    const authParameterName = '/finops/autopilot/auth';
    const env = {FINOPS_STORE:'dynamodb',FINOPS_TABLE:data.table.tableName,FINOPS_DATA_BUCKET:data.dataBucket.bucketName,
      FINOPS_KMS_KEY:data.key.keyArn,FINOPS_ENV:'production',FINOPS_ENABLE_LIVE:'true',FINOPS_AUTH_CONFIG:authParameterName,
      FINOPS_BEDROCK_ENABLED:'false',FINOPS_BEDROCK_REGION:'ap-south-1',FINOPS_BEDROCK_MODEL_ID:'global.anthropic.claude-opus-5-5',
      FINOPS_BEDROCK_TARGET_TYPE:'inference_profile',FINOPS_BEDROCK_ALLOW_GLOBAL:'true',FINOPS_BEDROCK_REQUIRE_GUARDRAIL:'true',FINOPS_BEDROCK_NATIVE_JSON:'true'};
    const makeFunction = (name:string,handler:string,timeout:number,memory=512) => {
      const group = new logs.LogGroup(this,name+'Logs',{retention:logs.RetentionDays.SIX_MONTHS,encryptionKey:data.key,removalPolicy:cdk.RemovalPolicy.RETAIN});
      const fn = new lambda.Function(this,name,{runtime:lambda.Runtime.PYTHON_3_12,architecture:lambda.Architecture.X86_64,
        handler,code,environment:env,timeout:cdk.Duration.seconds(timeout),memorySize:memory,logGroup:group,
        tracing:lambda.Tracing.ACTIVE});
      if(name !== 'Dispatcher') data.table.grantReadWriteData(fn);
      return fn;
    };
    // KMS grants for CloudWatch Logs need the regional service principal.
    data.key.addToResourcePolicy(new iam.PolicyStatement({principals:[new iam.ServicePrincipal(`logs.${this.region}.amazonaws.com`)],
      actions:['kms:Encrypt','kms:Decrypt','kms:ReEncrypt*','kms:GenerateDataKey*','kms:DescribeKey'],resources:['*'],
      conditions:{ArnLike:{'kms:EncryptionContext:aws:logs:arn':`arn:aws:logs:${this.region}:${this.account}:log-group:*`}}}));
    const apiFn = makeFunction('Api','services.api.lambda_handler.handler',28,1024);
    const worker = makeFunction('Collector','services.api.lambda_handler.worker',900,1024);
    apiFn.addEnvironment('FINOPS_COLLECTOR_PRINCIPAL',worker.role!.roleArn);
    const failed = makeFunction('MarkFailed','services.api.lambda_handler.workflow_failed',30);
    // Application runtimes cannot read/delete the management CloudTrail prefix.
    for(const prefix of ['curated','snapshot','report']) {
      data.dataBucket.grantRead(apiFn,`${prefix}/*`);
      data.dataBucket.grantPut(apiFn,`${prefix}/*`);
      data.dataBucket.grantRead(worker,`${prefix}/*`);
      data.dataBucket.grantPut(worker,`${prefix}/*`);
    }
    const secretArns = this.formatArn({service:'secretsmanager',resource:'secret',resourceName:'finops/*',arnFormat:cdk.ArnFormat.COLON_RESOURCE_NAME});
    apiFn.addToRolePolicy(new iam.PolicyStatement({actions:['secretsmanager:CreateSecret','secretsmanager:PutSecretValue'],resources:[secretArns]}));
    worker.addToRolePolicy(new iam.PolicyStatement({actions:['secretsmanager:GetSecretValue'],resources:[secretArns]}));
    data.key.grantEncryptDecrypt(apiFn); data.key.grantDecrypt(worker);
    apiFn.addToRolePolicy(new iam.PolicyStatement({actions:['ssm:GetParameter'],resources:[this.formatArn({service:'ssm',resource:'parameter',resourceName:'finops/autopilot/auth'})]}));
    worker.addToRolePolicy(new iam.PolicyStatement({actions:['sts:AssumeRole'],resources:['arn:aws:iam::*:role/FinOpsAutopilotReadOnly*'],conditions:{StringLike:{'sts:ExternalId':'finops-*'}}}));
    const workflowLogs = new logs.LogGroup(this,'WorkflowLogs',{retention:logs.RetentionDays.SIX_MONTHS,encryptionKey:data.key,removalPolicy:cdk.RemovalPolicy.RETAIN});
    const markFailed = new tasks.LambdaInvoke(this,'RecordFailure',{lambdaFunction:failed,payload:sfn.TaskInput.fromObject({tenant:sfn.JsonPath.stringAt('$.tenant'),job_id:sfn.JsonPath.stringAt('$.job_id')}),outputPath:'$.Payload',retryOnServiceExceptions:false});
    const collect = new tasks.LambdaInvoke(this,'RunJob',{lambdaFunction:worker,payloadResponseOnly:true,retryOnServiceExceptions:false});
    // Lambda rejects throttled invocations before user code executes; these retries do not replay paid inference.
    collect.addRetry({errors:['Lambda.TooManyRequestsException','Lambda.ServiceException','Lambda.AWSLambdaException','Lambda.SdkClientException'],interval:cdk.Duration.seconds(2),backoffRate:2,maxAttempts:6,jitterStrategy:sfn.JitterType.FULL});
    collect.addCatch(markFailed,{errors:['States.ALL'],resultPath:'$.failure'});
    const workflow = new sfn.StateMachine(this,'CollectionWorkflow',{definitionBody:sfn.DefinitionBody.fromChainable(collect),
      stateMachineType:sfn.StateMachineType.STANDARD,timeout:cdk.Duration.minutes(17),tracingEnabled:true,
      logs:{destination:workflowLogs,level:sfn.LogLevel.ALL,includeExecutionData:false},removalPolicy:cdk.RemovalPolicy.RETAIN});
    const dispatcher = makeFunction('Dispatcher','services.api.lambda_handler.dispatch',60);
    dispatcher.addEnvironment('FINOPS_WORKFLOW',workflow.stateMachineArn);
    workflow.grantStartExecution(dispatcher);
    const dlq = new sqs.Queue(this,'DispatchFailures',{encryption:sqs.QueueEncryption.KMS,encryptionMasterKey:data.key,
      enforceSSL:true,retentionPeriod:cdk.Duration.days(14),removalPolicy:cdk.RemovalPolicy.RETAIN});
    NagSuppressions.addResourceSuppressions(dlq,[{id:'AwsSolutions-SQS3',reason:'This is the DynamoDB stream failure destination itself. It is monitored and manually redriven; it has no queue consumer requiring another DLQ.'}]);
    dispatcher.addEventSource(new sources.DynamoEventSource(data.table,{startingPosition:lambda.StartingPosition.TRIM_HORIZON,
      batchSize:10,retryAttempts:5,bisectBatchOnError:true,reportBatchItemFailures:true,maxRecordAge:cdk.Duration.hours(23),
      onFailure:new sources.SqsDlq(dlq),filters:[lambda.FilterCriteria.filter({eventName:['INSERT'],dynamodb:{NewImage:{sk:{S:[{prefix:'job#'}]}}}})]}));
    const apiAccess = new logs.LogGroup(this,'ApiAccess',{retention:logs.RetentionDays.SIX_MONTHS,encryptionKey:data.key,removalPolicy:cdk.RemovalPolicy.RETAIN});
    const api = new apigw.LambdaRestApi(this,'ApiGateway',{handler:apiFn,proxy:true,endpointTypes:[apigw.EndpointType.REGIONAL],
      cloudWatchRole:true,deployOptions:{stageName:'prod',tracingEnabled:true,dataTraceEnabled:false,loggingLevel:apigw.MethodLoggingLevel.ERROR,
        throttlingBurstLimit:50,throttlingRateLimit:25,accessLogDestination:new apigw.LogGroupLogDestination(apiAccess),
        accessLogFormat:apigw.AccessLogFormat.custom('{"requestId":"$context.requestId","status":"$context.status","latency":"$context.responseLatency"}')}});
    NagSuppressions.addResourceSuppressionsByPath(this,'FinOpsApplication/ApiGateway/CloudWatchRole',[
      {id:'AwsSolutions-IAM4',reason:'The regional API Gateway account logging role uses the AWS API Gateway logging policy. It has no application data access.'}],true);
    const acl = new waf.CfnWebACL(this,'ApiFirewall',{scope:'REGIONAL',defaultAction:{allow:{}},visibilityConfig:{cloudWatchMetricsEnabled:true,metricName:'FinOpsFirewall',sampledRequestsEnabled:false},rules:[
      {name:'RequestRate',priority:0,action:{block:{}},statement:{rateBasedStatement:{limit:500,aggregateKeyType:'IP'}},visibilityConfig:{cloudWatchMetricsEnabled:true,metricName:'FinOpsRate',sampledRequestsEnabled:false}},
      {name:'CommonProtection',priority:1,overrideAction:{none:{}},statement:{managedRuleGroupStatement:{vendorName:'AWS',name:'AWSManagedRulesCommonRuleSet',ruleActionOverrides:[{name:'SizeRestrictions_BODY',actionToUse:{count:{}}}]}},visibilityConfig:{cloudWatchMetricsEnabled:true,metricName:'FinOpsCommon',sampledRequestsEnabled:false}}
    ]});
    new waf.CfnWebACLAssociation(this,'ApiFirewallAssociation',{webAclArn:acl.attrArn,resourceArn:api.deploymentStage.stageArn});
    const distribution = new cf.Distribution(this,'Web',{defaultRootObject:'index.html',
      // Legacy CloudFront access logs contain OAuth callback query strings.
      // Retain sanitized API logs/metrics; do not persist authorization codes.
      enableLogging:false,
      defaultBehavior:{origin:origins.S3BucketOrigin.withOriginAccessControl(webBucket),viewerProtocolPolicy:cf.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
        responseHeadersPolicy:cf.ResponseHeadersPolicy.SECURITY_HEADERS,cachePolicy:cf.CachePolicy.CACHING_OPTIMIZED},
      additionalBehaviors:{'v1/*':{origin:new origins.RestApiOrigin(api),viewerProtocolPolicy:cf.ViewerProtocolPolicy.HTTPS_ONLY,
        allowedMethods:cf.AllowedMethods.ALLOW_ALL,cachePolicy:cf.CachePolicy.CACHING_DISABLED,originRequestPolicy:cf.OriginRequestPolicy.ALL_VIEWER_EXCEPT_HOST_HEADER,
        responseHeadersPolicy:cf.ResponseHeadersPolicy.SECURITY_HEADERS}},priceClass:cf.PriceClass.PRICE_CLASS_200});
    const origin = 'https://'+distribution.distributionDomainName;
    const domain = new cognito.UserPoolDomain(this,'LoginDomain',{userPool:data.pool,cognitoDomain:{domainPrefix:`finops-${this.account}-${this.region}`}});
    const poolClient = new cognito.UserPoolClient(this,'WebClient',{userPool:data.pool,generateSecret:false,preventUserExistenceErrors:true,
      accessTokenValidity:cdk.Duration.hours(1),idTokenValidity:cdk.Duration.hours(1),refreshTokenValidity:cdk.Duration.days(1),
      oAuth:{flows:{authorizationCodeGrant:true},callbackUrls:[origin+'/v1/auth/callback'],logoutUrls:[origin+'/'],
        scopes:[cognito.OAuthScope.OPENID,cognito.OAuthScope.EMAIL,cognito.OAuthScope.PROFILE,cognito.OAuthScope.COGNITO_ADMIN]},
      supportedIdentityProviders:[cognito.UserPoolClientIdentityProvider.COGNITO]});
    new ssm.StringParameter(this,'AuthRuntimeConfiguration',{parameterName:authParameterName,
      stringValue:cdk.Stack.of(this).toJsonString({origin,client_id:poolClient.userPoolClientId,domain:domain.baseUrl()})});
    const site = new deployment.BucketDeployment(this,'PublishFrontend',{sources:[deployment.Source.asset(path.resolve(__dirname,'../../apps/web/dist'))],
      destinationBucket:webBucket,distribution,distributionPaths:['/*'],prune:true,memoryLimit:512});
    NagSuppressions.addResourceSuppressions(site,[{id:'AwsSolutions-IAM4',reason:'CDK asset provider uses the AWS-managed Lambda basic execution policy; application functions have dedicated roles.'},{id:'AwsSolutions-IAM5',reason:'CDK frontend deployment provider requires object-prefix operations and CloudFront invalidation on the generated distribution.'}],true);
    const assetProvider = this.node.findAll().find(node=>node instanceof lambda.Function && node.node.id.startsWith('Custom::CDKBucketDeployment'));
    if(assetProvider) NagSuppressions.addResourceSuppressions(assetProvider,[{id:'AwsSolutions-L1',reason:'Runtime is selected and maintained by the pinned CDK BucketDeployment provider.'},
      {id:'AwsSolutions-IAM4',reason:'The CDK asset provider uses AWSLambdaBasicExecutionRole for deployment diagnostics.'},
      {id:'AwsSolutions-IAM5',reason:'CDK provider manages objects in the generated frontend/asset buckets and invalidates the generated distribution. Its code is supplied by pinned aws-cdk-lib.'}],true);
    const database = new glue.CfnDatabase(this,'BillingCatalog',{catalogId:this.account,databaseInput:{name:'finops_billing'}});
    new glue.CfnTable(this,'BillingTable',{catalogId:this.account,databaseName:database.ref,tableInput:{name:'billing_snapshots',tableType:'EXTERNAL_TABLE',
      parameters:{classification:'json','projection.enabled':'true','projection.tenant.type':'injected',
        'projection.connection.type':'injected','projection.snapshot.type':'injected',
        'storage.location.template':'s3://'+data.dataBucket.bucketName+'/curated/tenant=${tenant}/connection=${connection}/snapshot=${snapshot}/'},
      partitionKeys:[{name:'tenant',type:'string'},{name:'connection',type:'string'},{name:'snapshot',type:'string'}],
      storageDescriptor:{location:`s3://${data.dataBucket.bucketName}/curated/`,
        inputFormat:'org.apache.hadoop.mapred.TextInputFormat',outputFormat:'org.apache.hadoop.hive.ql.io.HiveIgnoreKeyTextOutputFormat',
        serdeInfo:{serializationLibrary:'org.openx.data.jsonserde.JsonSerDe'},columns:[
          {name:'date',type:'string'},{name:'service',type:'string'},{name:'amount',type:'decimal(38,18)'},{name:'currency',type:'string'},
          {name:'provider',type:'string'},{name:'connection_id',type:'string'},{name:'snapshot_id',type:'string'},{name:'collected_at',type:'string'}]}}});
    const workgroup = new athena.CfnWorkGroup(this,'BillingQueries',{name:'finops-billing',recursiveDeleteOption:false,
      workGroupConfiguration:{enforceWorkGroupConfiguration:true,publishCloudWatchMetricsEnabled:true,bytesScannedCutoffPerQuery:1024**3,
        resultConfiguration:{outputLocation:`s3://${data.dataBucket.bucketName}/athena-results/`,encryptionConfiguration:{encryptionOption:'SSE_KMS',kmsKey:data.key.keyArn}}}});
    workgroup.applyRemovalPolicy(cdk.RemovalPolicy.RETAIN);
    new cw.Alarm(this,'DeadLetterAlarm',{metric:dlq.metricApproximateNumberOfMessagesVisible(),threshold:1,evaluationPeriods:1,treatMissingData:cw.TreatMissingData.NOT_BREACHING});
    new cw.Alarm(this,'ApiErrorAlarm',{metric:apiFn.metricErrors(),threshold:3,evaluationPeriods:1,treatMissingData:cw.TreatMissingData.NOT_BREACHING});
    new cw.Alarm(this,'WorkflowFailureAlarm',{metric:workflow.metricFailed(),threshold:1,evaluationPeriods:1,treatMissingData:cw.TreatMissingData.NOT_BREACHING});
    // First-party cookie sessions are checked in FastAPI; OAuth endpoints must be publicly reachable.
    NagSuppressions.addResourceSuppressions(api,[{id:'AwsSolutions-APIG4',reason:'FastAPI checks every business route using a server-side session and membership. Only health and OAuth routes are unauthenticated.'},
      {id:'AwsSolutions-COG4',reason:'Cognito uses a server-side PKCE callback and HttpOnly sessions; native Cognito JWT authorizers do not validate these cookies.'},
      {id:'AwsSolutions-APIG2',reason:'FastAPI Pydantic enforces strict request schemas and a 2MB body limit before handlers; Gateway request-body tracing is disabled.'}],true);
    NagSuppressions.addResourceSuppressions(distribution,[{id:'AwsSolutions-CFR1',reason:'Global access is required for customer sign-in; tenant data processing remains in Mumbai.'},
      {id:'AwsSolutions-CFR2',reason:'Regional WAF protects every API endpoint including the default API domain. Static CloudFront origin contains no private business data.'},
      {id:'AwsSolutions-CFR3',reason:'Legacy edge access logs include OAuth callback query strings. They are disabled to avoid retaining authorization codes; sanitized API access logs and CloudFront metrics remain enabled. Add configurable-field v2 edge delivery before enabling edge request logs.'},
      {id:'AwsSolutions-CFR4',reason:'AWS default CloudFront certificate is used until the customer supplies a custom domain and ACM certificate.'}]);
    for(const fn of [apiFn,worker,failed,dispatcher]) NagSuppressions.addResourceSuppressions(fn,[
      {id:'AwsSolutions-L1',reason:'Python 3.12 is pinned for the tested manylinux dependency bundle; upgrade together with the runtime lock and tests.'},
      {id:'AwsSolutions-IAM4',reason:'CDK adds the AWS-managed Lambda tracing/basic logging policies. Service data grants are scoped to project resources.'},
      {id:'AwsSolutions-IAM5',reason:'Tenant/customer IDs and Secrets Manager suffixes are dynamic. Access is limited to project buckets/table, finops/* secrets, and externally trusted FinOpsAutopilotReadOnly roles.'}],true);
    NagSuppressions.addResourceSuppressions(workflow,[{id:'AwsSolutions-IAM5',reason:'Step Functions logging requires delivery APIs without resource-level authorization; Lambda invoke grants target project functions.'}],true);
    new cdk.CfnOutput(this,'ApplicationUrl',{value:origin});
    new cdk.CfnOutput(this,'CollectorRoleArn',{value:worker.role!.roleArn});
    new cdk.CfnOutput(this,'ApiUrl',{value:api.url});
    new cdk.CfnOutput(this,'TableName',{value:data.table.tableName});
    new cdk.CfnOutput(this,'AnalyticsBucket',{value:data.dataBucket.bucketName});
  }
}
