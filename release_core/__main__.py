"""Source-bound artifact checks for explicitly registered owners; never uploads."""

import argparse
import json
from pathlib import Path
import sys

from .files import verify_artifact_files
from .registered import RELEASE_REGISTRY


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    verify = commands.add_parser("verify-files")
    verify.add_argument("--repository", required=True)
    verify.add_argument("--commit", required=True)
    verify.add_argument("--source-root", type=Path, required=True)
    verify.add_argument("--wheel", type=Path, required=True)
    verify.add_argument("--sdist", type=Path, required=True)
    args = parser.parse_args(argv)
    policy = RELEASE_REGISTRY.resolve(args.repository)
    proof = verify_artifact_files(
        args.wheel,
        args.sdist,
        args.commit,
        policy,
        source_root=args.source_root,
    )
    json.dump(proof, sys.stdout, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
