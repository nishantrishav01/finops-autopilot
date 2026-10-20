# Bedrock setup for the local application

The same advisory layer is packaged in the CDK deployment. The initial cloud release deliberately leaves inference disabled and attaches no Bedrock invocation permissions. Configure the published guardrail, restricted worker IAM, entitlement and pinned runtime through a reviewed CDK release before enabling; do not treat local environment variables as a cloud deployment mechanism. See [deployment enablement](DEPLOYMENT.md).

Verified documentation: 20 October 2026. This guide describes the implemented local integration. It does not imply that an AWS account, guardrail or model entitlement has been provisioned.

## Selected model and processing boundary

| Setting | Selected value |
|---|---|
| Request source | Mumbai, `ap-south-1` |
| API | Bedrock Runtime `Converse` through the Python SDK |
| Model route | `global.anthropic.claude-opus-5-5` |
| Model | Claude Opus 5.5 |
| Output | Native JSON schema plus strict local validation |
| Reasoning effort | Low; adaptive thinking remains enabled |
| Output limit | Client policy, default 4,096 tokens |
| Input accounting | Conservative byte-based reservation; actual usage recorded afterwards |
| Inference retry | One SDK attempt; no automatic paid repair/fallback call |

The current [AWS model card](https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-anthropic-claude-opus-5-5.html) lists Mumbai as global-inference only and CountTokens as unsupported. This route can process prompts and responses outside India. It is unsuitable for an India-only requirement. Native structured output is supported on Bedrock Runtime; the app uses `outputConfig.textFormat` and validates references and actions independently. [AWS structured output documentation](https://docs.aws.amazon.com/bedrock/latest/userguide/structured-output.html) describes schema restrictions and possible first-use compilation latency.

The operator allows the global capability, as requested. **Every client starts disabled with India-only policy.** A workspace administrator must explicitly select global processing, approve the disclosure and enable that workspace. A different client never inherits the approval. Changing the model, source region, guardrail version, schema mode, prompt version or transfer version invalidates prior approval. There is no automatic switch to a different model or region.

## Prepare AWS access and the guardrail

1. Install the optional SDK dependencies with `.\.venv\Scripts\python.exe -m pip install -r requirements-cloud.txt`. This workspace already has them installed.
2. Use an operator-managed short-lived AWS credential session or workload role. Boto3 resolves the standard credential chain, including an explicitly selected `AWS_PROFILE`. Never put access keys, Azure client secrets or GCP private keys in the web application. Bedrock runs in the platform's AWS environment even when the customer account is on Azure or GCP.
3. Have the AWS account owner verify the selected model's availability, entitlement, current terms, quotas and global-route permissions. Model discovery alone does not prove inference entitlement. Do not grant subscription or model-enablement administration to the application runtime.
4. Create and evaluate a guardrail for prompt attacks, sensitive information and appropriate content policies. Publish a **numbered version** in the request region; record its ID and version. The app rejects `DRAFT`. Account for each policy's regional and cross-region behavior and any additional charges. Guardrail filtering cannot prove financial accuracy or legal compliance. See [Bedrock Guardrails](https://docs.aws.amazon.com/bedrock/latest/userguide/guardrails.html).
5. Give the runtime least-privilege `bedrock:InvokeModel` permissions on the exact approved inference profile and required backing foundation-model resources, `bedrock:GetInferenceProfile` for route verification, and `bedrock:ApplyGuardrail` for the configured guardrail where required. The preflight additionally reads `bedrock:GetGuardrail`; the application does not administer guardrails. If using a foundation-model target later, route inspection needs `bedrock:GetFoundationModel`. Apply the current [cross-region inference IAM requirements](https://docs.aws.amazon.com/bedrock/latest/userguide/cross-region-inference.html), including destination-resource/SCP handling; a blanket source-region deny can break global inference.

No IAM policies, AWS resources or Marketplace subscriptions were created by this implementation. The runtime has no cloud-change tools. Its Bedrock credential role should be separate from customer billing reader roles.

## Configure the local process

Stop the existing server and run these in the terminal that will launch it. Replace guardrail placeholders with real, reviewed values. `.env.example` documents settings; `.env` is **not** automatically loaded.

```powershell
cd 'E:\Websites\FinOps Autopilot'
$env:FINOPS_BEDROCK_REGION = 'ap-south-1'
$env:FINOPS_BEDROCK_MODEL_ID = 'global.anthropic.claude-opus-5-5'
$env:FINOPS_BEDROCK_TARGET_TYPE = 'inference_profile'
$env:FINOPS_BEDROCK_ALLOW_GLOBAL = 'true'
$env:FINOPS_BEDROCK_REQUIRE_GUARDRAIL = 'true'
$env:FINOPS_BEDROCK_GUARDRAIL_ID = '<your-published-guardrail-id>'
$env:FINOPS_BEDROCK_GUARDRAIL_VERSION = '<your-numbered-version>'
$env:FINOPS_BEDROCK_NATIVE_JSON = 'true'

# Purely local configuration check:
.\.venv\Scripts\python.exe -m scripts.bedrock_preflight --configuration-only
# Signed read-only model-route and guardrail metadata checks; no model call:
.\.venv\Scripts\python.exe -m scripts.bedrock_preflight

$env:FINOPS_BEDROCK_ENABLED = 'true'
.\scripts\start.ps1
```

Preflight prints sanitized status and possible processing regions, never credentials or full SDK exceptions. It does not send evidence, invoke the model, approve any client, verify paid inference or modify AWS. `READY_UNVERIFIED` in the UI means local admission checks passed; it is intentionally not a claim that live AWS access works.

`FINOPS_ENABLE_LIVE` controls billing collection separately. Imported source evidence can receive AI guidance without enabling live cloud collection. `FINOPS_ENV=production` forces the guardrail requirement, but setting this flag does not make the local edition production-ready. Keep it on loopback.

## Enable one approved client and request a draft

1. Open the client's separate workspace, then **Settings → Amazon Bedrock · client governance**.
2. Review the model, route, disclosure and customer contract/security approval. If international processing is disallowed, leave the workspace disabled and India-only.
3. For an approved client, select **Client-approved global AWS processing**, choose the allowed AWS/Azure/GCP evidence sources and quotas, explicitly check the approval, and enable guidance. Synthetic sample inference needs a separate checkbox. Saving settings never invokes a model.
4. Open an opportunity and run **Assess evidence**. Then use **Bedrock guidance → Generate Bedrock guidance**. This user-triggered step sends evidence and may incur AWS charges.
5. Review the draft's fact references, selected investigation steps, open questions and trace metadata. Record Helpful/Inaccurate/Unsafe feedback. The existing deterministic assessment and human plan review remain authoritative.

All three cloud providers use the same minimized evidence contract. Source estimate amounts stay in a fact panel; the model cannot replace them or claim realized savings. It selects from application-owned investigation actions and explains supplied facts. No account IDs, resource IDs, owner names, tags, raw provider response, customer free text, credentials or internal model reasoning are sent as source facts. Amounts, utilization and operating context can still be commercially sensitive, so minimization does not remove the need for customer approval.

## Failure and spending behavior

| Result | Required response |
|---|---|
| Disabled / client approval required | Complete the appropriate operator and client steps; do not bypass policy |
| Reapproval required | Review changed processing settings and save a fresh administrator approval |
| Residency denied | Keep AI disabled or select a separately verified eligible India route; global Opus cannot satisfy India-only |
| Configuration required | Install SDK or configure the pinned guardrail/model settings |
| Bedrock unavailable | Verify credential session, IAM, model entitlement, route and guardrail without copying secrets into logs |
| Model response rejected | Keep deterministic assessment; investigate validation/guardrail/length failures; no automatic repair call |
| Context changed | Discard the draft and reload current evidence/policy before another explicit request |
| Quota reached | Wait for the next UTC day or have the client administrator review the limit |

Admission reserves serialized-input UTF-8 bytes plus a protocol allowance and the maximum output tokens. This is a conservative local heuristic, **not an AWS token count or rupee budget**. Failed/interrupted requests retain reservations for the UTC day; validated responses record SDK input/output usage. A timeout may still have incurred provider charges. Same-context drafts are reused for one hour within the same tenant/objective. Idempotent job keys avoid duplicate initiation; retries after an uncertain timeout need billing reconciliation.

Daily requests, reservations and feedback are visible in Settings. The current app records token usage, not verified invoice cost. Production needs authoritative billing reconciliation, fleet-wide admission controls and account budgets in addition to per-client limits.

For rollout, security and Indian customer obligations, use [the production and India guide](BEDROCK_PRODUCTION_INDIA.md). For what was actually exercised, see [validation](VALIDATION.md).
