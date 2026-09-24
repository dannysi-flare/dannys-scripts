#!/usr/bin/env python3
"""One-off: build vocabulary.json from vinny's enum + draft-driver's list.

Both files mix quote styles - the apostrophe names (PETITIONER'S_*) are double-quoted,
everything else single-quoted - so every pattern here is quote-agnostic.
"""
import json, re, subprocess

def show(repo, ref):
    return subprocess.run(['git', '-C', repo, 'show', ref], capture_output=True, text=True, check=True).stdout

v = show('/Users/dannysivan/src/vinny', 'origin/main:libs/data-collection-types/src/lib/types.dto.ts')
d = show('/Users/dannysivan/src/draft-driver-100x', 'origin/main:src/draft_driver/pipeline/consts.py')

LITERAL = re.compile(r"""^\s*(['"])(.+?)\1\s*,?\s*$""", re.M)

def literals(source, start, end):
    i = source.index(start)
    return [m.group(2) for m in LITERAL.finditer(source[i + len(start):source.index(end, i)])]

buckets = literals(v, 'FLARE_BUCKET_VALUES = [', '] as const')
subs_vinny = literals(v, 'FLARE_SUB_BUCKET_VALUES = [', '] as const')
sections = literals(v, 'FLARE_QUESTIONNAIRE_VALUES = [', '] as const')
subs_ddr = literals(d, 'VALID_FLARE_SUB_BUCKETS = {', '\n}')

FIELD = re.compile(r"""(\w+):\s*\n?\s*(['"])((?:[^\\]|\\.)*?)\2""", re.S)

def descriptions(block):
    out = {}
    for raw in re.finditer(r'\{(.*?)\}', block, re.S):
        fields = {k: re.sub(r'\s*\n\s*', ' ', val) for k, _, val in FIELD.findall(raw.group(1))}
        if 'name' in fields:
            out[fields['name']] = fields.get('description', '')
    return out

bucket_desc = descriptions(v[v.index('FLARE_BUCKET_METADATA'):v.index('FLARE_SUB_BUCKET_METADATA')])
sub_desc = descriptions(v[v.index('FLARE_SUB_BUCKET_METADATA'):])

seen, subs = set(), []
for name in subs_vinny + subs_ddr:
    if name not in seen:
        seen.add(name)
        subs.append(name)

nodes = (
    [{'type': 'BUCKET', 'name': n, 'description': bucket_desc.get(n, '')} for n in buckets]
    + [{'type': 'SUB_BUCKET', 'name': n, 'description': sub_desc.get(n, '')} for n in subs]
    + [{'type': 'SECTION', 'name': n, 'description': ''} for n in sections]
)

with open('/Users/dannysivan/src/dannys-scripts/as-4540-questionnaire-bucket-vocabulary/vocabulary.json', 'w') as f:
    json.dump(nodes, f, indent=2, ensure_ascii=False)
    f.write('\n')

for t in ('BUCKET', 'SUB_BUCKET', 'SECTION'):
    rows = [n for n in nodes if n['type'] == t]
    print(f"{t}: {len(rows)}, {sum(1 for r in rows if not r['description'])} blank description")
print("total nodes:", len(nodes))
print("draft-driver names missing from vinny:", sorted(set(subs_ddr) - set(subs_vinny)) or "none")
print("vinny names missing from draft-driver:", sorted(set(subs_vinny) - set(subs_ddr)))
