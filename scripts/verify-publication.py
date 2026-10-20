"""Fail closed on risky tracked files and common credential patterns; never print values."""
import re
import subprocess
from pathlib import Path

files=subprocess.check_output(['git','ls-files','-z']).decode().split('\0')
blocked=[]
patterns=[re.compile(rb'\b(?:AKIA|ASIA)[A-Z0-9]{16}\b'),
    re.compile(rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),
    re.compile(rb'gh[pousr]_[A-Za-z0-9]{30,}'),
    re.compile(rb'github_pat_[A-Za-z0-9_]{30,}')]
for name in filter(None,files):
    path=Path(name)
    if any(part in ('data','.aws','.cache','.venv','cdk.out','node_modules','artifacts','outputs') for part in path.parts) or (path.name.startswith('.env') and path.name!='.env.example') or path.suffix in ('.db','.sqlite','.pem','.key','.pfx','.p12') or name=='docs/original-specification.md':
        blocked.append((name,'private/generated file'))
        continue
    if path.suffix not in ('.png','.woff2') and path.is_file():
        data=path.read_bytes()
        if any(pattern.search(data) for pattern in patterns): blocked.append((name,'possible credential material'))
if blocked:
    for name,reason in blocked: print(f'BLOCKED {name}: {reason}')
    raise SystemExit(1)
print(f'Publication checks passed for {len(list(filter(None,files)))} tracked files. Manual data review is still required.')
