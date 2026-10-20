"""Read-only Bedrock setup checks; never sends evidence or invokes a model."""
import argparse
import json
import sys

from services.api import advisor


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--configuration-only', action='store_true', help='Do not contact AWS.')
    args = parser.parse_args()
    cfg = advisor.runtime_config()
    report = {'region': cfg['region'], 'model_id': cfg['model_id'],
        'configuration_ready': cfg['configuration_ready'], 'issues': cfg['issues'],
        'global_capability_allowed': cfg['allow_global'], 'credentials_verified': False,
        'route_metadata_verified': False, 'guardrail_exists': False,
        'inference_verified': False, 'model_invoked': False,
        'client_processing_approval': 'Not granted by preflight. Approve separately in each client workspace.'}
    if not args.configuration_only and cfg['configuration_ready']:
        try:
            control, _ = advisor.clients(cfg)
            # This signed read proves control-plane credentials, not InvokeModel entitlement.
            report['possible_destination_regions'] = advisor.verify_route(control, cfg,
                {'residency_mode': 'global_approved' if cfg['allow_global'] else 'india_only'})
            report.update(credentials_verified=True, route_metadata_verified=True)
            if cfg['guardrail_id']:
                control.get_guardrail(guardrailIdentifier=cfg['guardrail_id'], guardrailVersion=cfg['guardrail_version'])
                report['guardrail_exists'] = True
        except Exception:
            report['issues'] = [*report['issues'], 'AWS metadata verification failed. Check the active SDK credential session, source-region permissions, profile ID and numbered guardrail. No inference was attempted.']
    print(json.dumps(report, indent=2))
    return 0 if not report['issues'] else 1


if __name__ == '__main__':
    sys.exit(main())
