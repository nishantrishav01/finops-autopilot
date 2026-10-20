"""Fetch public AWS price lists; no credentials or customer account calls."""
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
from pathlib import Path
from urllib.request import urlopen

ROOT = Path('.cache/pricing')
SERVICES = ['AmazonDynamoDB', 'AWSLambda', 'AmazonApiGateway', 'AmazonS3',
    'AmazonStates', 'AWSQueueService', 'AmazonCloudWatch', 'AmazonCognito',
    'awskms', 'AWSSecretsManager', 'awswaf', 'AmazonAthena',
    'AWSGlue', 'AWSEvents', 'AmazonCloudFront', 'AmazonRoute53', 'AmazonBedrock', 'AWSDataTransfer']


def fetch(service):
    regions = ['ap-south-1', ''] if service not in ['AmazonCloudFront', 'AmazonRoute53'] else ['']
    for region in regions:
        url = f'https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/{service}/current/{region+"/" if region else ""}index.json'
        try:
            with urlopen(url, timeout=35) as response:
                raw = response.read(40_000_001)
            if len(raw) > 40_000_000:
                return service, {'error': 'Catalog exceeded fetch limit'}
            doc = json.loads(raw)
            (ROOT / f'{service}.json').write_bytes(raw)
            return service, {'url': url, 'publicationDate': doc.get('publicationDate'), 'products': len(doc.get('products', {}))}
        except Exception as exc:
            last = type(exc).__name__
    return service, {'error': last}


def main():
    ROOT.mkdir(parents=True, exist_ok=True)
    metadata = {}
    with ThreadPoolExecutor(max_workers=6) as pool:
        for future in as_completed([pool.submit(fetch, service) for service in SERVICES]):
            service, result = future.result(); metadata[service] = result
            print(service, json.dumps(result), flush=True)
    (ROOT/'catalogs.json').write_text(json.dumps(metadata, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
