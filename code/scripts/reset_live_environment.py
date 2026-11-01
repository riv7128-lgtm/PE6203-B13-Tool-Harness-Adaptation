"""Restart only the selected stage's inspected MCP processes before a cell."""
import argparse
import json
from urllib.request import Request, build_opener, ProxyHandler
urlopen = build_opener(ProxyHandler({})).open

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--endpoint', required=True)
    args = parser.parse_args()
    base = args.endpoint.split('/mcp')[0]
    if not base.startswith('http://127.0.0.1:'):
        raise SystemExit('Only project localhost endpoints are permitted')
    with urlopen(Request(base + '/reset', data=b'{}', headers={'Content-Type': 'application/json'}), timeout=120) as response:
        result = json.load(response)
    if result.get('status') != 'reset':
        raise SystemExit('Stage reset did not complete')
    print(json.dumps(result))
