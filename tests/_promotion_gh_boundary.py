"""Owned local-Git command boundary; never contacts GitHub or the network."""

import json
import os
import subprocess
import sys
from pathlib import Path


def git(root, *args):
    return subprocess.check_output(
        ['/usr/bin/git', '-C', str(root), *args], text=True, timeout=20
    ).strip()


def main():
    root = Path(os.environ['PROMOTION_FIXTURE'])
    args = sys.argv[1:]
    with (root / 'calls.jsonl').open('a') as stream:
        stream.write(json.dumps(args) + '\n')
    origin = root / 'origin.git'
    seed = root / 'seed'
    mode = os.environ['PROMOTION_MODE']
    if args[:2] == ['pr', 'list']:
        if mode == 'race':
            git(origin, 'update-ref', 'refs/heads/develop', os.environ['FUTURE_SHA'])
        print('1')
        return 0
    if args[:2] != ['pr', 'merge']:
        raise RuntimeError(f'Unexpected boundary command: {args!r}')
    expected = os.environ['TAG_SHA']
    if '--admin' in args or '--merge' not in args:
        print('Non-normal merge refused by owned boundary', file=sys.stderr)
        return 41
    if '--match-head-commit' not in args:
        print('Missing expected-head protection', file=sys.stderr)
        return 42
    provided = args[args.index('--match-head-commit') + 1]
    if provided != expected or git(origin, 'rev-parse', 'refs/heads/develop') != provided:
        print('Head changed: expected-head merge refused', file=sys.stderr)
        return 43
    git(seed, 'checkout', 'main')
    git(seed, 'merge', '--no-ff', expected, '-m', 'Owned normal promotion fixture')
    git(seed, 'push', 'origin', 'main')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
