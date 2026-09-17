#!/usr/bin/env bash
# Keep the shared runner user's npm cache path a real, owned directory.
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
exec python3 "${script_dir}/runner_npm_cache_preflight.py"
