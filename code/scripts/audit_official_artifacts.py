"""Validate selective patching on literal metadata in official mutation hunks.

This audit does NOT run an LLM or MCP task and produces no TF, PE or ECS.
Extraction is conservative and coverage is reported, not silently generalized.
"""
import argparse
import copy
import hashlib
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from harness_adapt.literal_parser import LiteralError, parse_data_literal
from harness_adapt.changes import detect_changes
from harness_adapt.patch import selective_patch


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def extract_pairs(repo):
    files = sorted((repo / 'src/custom/data/mutation').rglob('evolution.json'))
    pairs, rejected = [], []
    total = 0
    for path in files:
        data = json.loads(path.read_text(encoding='utf-8'))
        for server, tools in data.items():
            if not isinstance(tools, dict):
                continue
            for tool, record in tools.items():
                if not isinstance(record, dict):
                    continue
                for index, hunk in enumerate(record.get('diff_hunks', [])):
                    if not isinstance(hunk, dict):
                        continue
                    total += 1
                    old, new = hunk.get('old_code', ''), hunk.get('new_code', '')
                    source = {'file': str(path.relative_to(repo)), 'sha256': sha256(path),
                              'server': server, 'tool': tool, 'hunk_index': index}
                    if not all(isinstance(x, str) and x.strip().startswith('{')
                               and 'inputSchema' in x for x in (old, new)):
                        rejected.append({**source, 'reason': 'not_complete_tool_literal_pair'})
                        continue
                    try:
                        a, b = parse_data_literal(old), parse_data_literal(new)
                        for obj in (a, b):
                            if not isinstance(obj, dict) or not isinstance(obj.get('name'), str) \
                                    or not isinstance(obj.get('inputSchema'), dict):
                                raise LiteralError('Tool metadata shape required')
                        pairs.append({**source, 'old_tool': a, 'new_tool': b})
                    except (LiteralError, IndexError, TypeError, ValueError) as exc:
                        rejected.append({**source, 'reason': 'unsupported_literal',
                                         'detail': str(exc)[:180]})
    return files, total, pairs, rejected


def audit(repo, output):
    files, total, pairs, rejected = extract_pairs(repo)
    rows = []
    sentinel = {'name': 'audit__unchanged_control', 'description': 'Local invariant control',
                'inputSchema': {'type': 'object', 'properties': {}}}
    for pair in pairs:
        def harness(tool):
            obj = copy.deepcopy(tool)
            obj['name'] = pair['server'] + '__' + obj['name']
            obj['server'] = pair['server']
            return {'tools': [obj, copy.deepcopy(sentinel)], 'usage_rules': {},
                    'routing': {obj['name']: pair['server'], sentinel['name']: 'local_audit'},
                    'global_rules': ['Keep unrelated knowledge unchanged.']}
        old, new = harness(pair['old_tool']), harness(pair['new_tool'])
        start = time.perf_counter()
        result = selective_patch(old, new)
        elapsed = time.perf_counter() - start
        def bytes_of(value):
            return len(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                  separators=(',', ':')).encode('utf-8'))
        new_name = new['tools'][0]['name']
        changed_tool = next((x for x in result['tools'] if x['name'] == new_name), None)
        unchanged = next((x for x in result['tools'] if x['name'] == sentinel['name']), None)
        change = detect_changes(old, new)
        row = {k: pair[k] for k in ('file', 'sha256', 'server', 'tool', 'hunk_index')}
        row.update({'changed_tool_matches_target': changed_tool == new['tools'][0],
                    'unchanged_control_preserved': unchanged == sentinel,
                    'global_rules_preserved': result['global_rules'] == old['global_rules'],
                    'source_input_unchanged': old == harness(pair['old_tool']),
                    'idempotent': selective_patch(result, new) == result,
                    'affected': change.get('affected', []),
                    'adaptation_seconds': elapsed,
                    'target_tool_json_bytes': bytes_of(new['tools'][0]),
                    'target_harness_json_bytes': bytes_of(new)})
        rows.append(row)
    assertions = ['changed_tool_matches_target', 'unchanged_control_preserved',
                  'global_rules_preserved', 'source_input_unchanged', 'idempotent']
    summary = {'evidence_type': 'OFFICIAL_METADATA_STATIC_AUDIT',
               'not_task_evaluation': True, 'tf': None, 'pe': None, 'ecs': None,
               'source_files': len(files), 'total_diff_hunks': total,
               'accepted_literal_pairs': len(pairs), 'rejected_hunks': len(rejected),
               'assertions_per_pair': len(assertions),
               'passed_assertions': sum(bool(r[k]) for r in rows for k in assertions),
               'failed_assertions': sum(not r[k] for r in rows for k in assertions),
               'coverage_limit': 'Complete JSON-like JS tool literals only. '
               'Python/TypeScript/function-body hunks and additions/deletions without '
               'paired complete literals are excluded. The unchanged control is local, '
               'not a measured unaffected benchmark task.'}
    output.mkdir(parents=True, exist_ok=True)
    for name, value in [('summary.json', summary), ('pairs.json', pairs),
                        ('audit_rows.json', rows), ('excluded_hunks.json', rejected)]:
        (output / name).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--official-repo', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.official_repo, args.output)
    print(json.dumps(result, indent=2))
    sys.exit(1 if result['failed_assertions'] or not result['accepted_literal_pairs'] else 0)
