# Security reporting

Do not put customer data, AWS keys, session cookies, raw billing exports or Bedrock prompts into public GitHub issues. Report security concerns privately to the repository owner through GitHub's private vulnerability reporting channel where enabled, or an agreed private customer support channel.

The public source excludes local credentials, databases, generated cloud outputs and the original attached specification. Revoke an exposed AWS key immediately in its owning account; deleting it from Git history is not sufficient. Rotate the application session and inspect CloudTrail when appropriate.

Before a regulated customer rollout, complete the acceptance gates in `docs/DEPLOYMENT.md` and `docs/BEDROCK_PRODUCTION_INDIA.md`. These documents describe engineering controls and outstanding work; they do not certify compliance for every Indian customer or industry.
