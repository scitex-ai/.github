#!/usr/bin/env bash
# Keep the shared runner user's npm cache path a real, owned directory.
set -euo pipefail

cache_home="${HOME:?HOME must be set}/.npm"
lock_file="/tmp/scitex-runner-npm-cache-${UID}.lock"

# Multiple org runners share HOME on a host.  Serialize the inspect/move/create
# sequence so two jobs cannot quarantine or replace each other's new path.
exec 9>"$lock_file"
flock -x 9

current_uid="$(id -u)"
current_gid="$(id -g)"

if [[ -d "$cache_home" && ! -L "$cache_home" ]]; then
    cache_uid="$(stat -c %u -- "$cache_home")"
    cache_gid="$(stat -c %g -- "$cache_home")"
    if [[ "$cache_uid:$cache_gid" != "$current_uid:$current_gid" ]]; then
        printf '::error title=npm cache ownership::%s is owned by uid:gid %s:%s; expected %s:%s; refusing to mutate it\n' \
            "$cache_home" "$cache_uid" "$cache_gid" "$current_uid" "$current_gid" >&2
        exit 1
    fi
    printf 'npm cache preflight: existing owned directory: %s\n' "$cache_home"
    exit 0
fi

if [[ -e "$cache_home" || -L "$cache_home" ]]; then
    artifact_uid="$(stat -c %u -- "$cache_home")"
    if [[ "$artifact_uid" != "$current_uid" ]]; then
        printf '::error title=npm cache ownership::%s is a non-directory owned by uid %s; expected %s; refusing to quarantine it\n' \
            "$cache_home" "$artifact_uid" "$current_uid" >&2
        exit 1
    fi

    stamp="$(date -u +%Y%m%dT%H%M%SZ)"
    quarantine="${cache_home}.quarantine-${stamp}-$$"
    if [[ -e "$quarantine" || -L "$quarantine" ]]; then
        printf '::error title=npm cache quarantine collision::refusing to overwrite %s\n' "$quarantine" >&2
        exit 1
    fi
    mv -- "$cache_home" "$quarantine"
    printf '::warning title=npm cache repaired::quarantined non-directory cache artifact at %s\n' "$quarantine"
fi

install -d -m 0755 -- "$cache_home"

if [[ ! -d "$cache_home" || -L "$cache_home" ]]; then
    printf '::error title=npm cache repair::%s is not a real directory after repair\n' "$cache_home" >&2
    exit 1
fi
cache_uid="$(stat -c %u -- "$cache_home")"
cache_gid="$(stat -c %g -- "$cache_home")"
if [[ "$cache_uid:$cache_gid" != "$current_uid:$current_gid" ]]; then
    printf '::error title=npm cache ownership::recreated %s has uid:gid %s:%s; expected %s:%s\n' \
        "$cache_home" "$cache_uid" "$cache_gid" "$current_uid" "$current_gid" >&2
    exit 1
fi

printf 'npm cache preflight: ready: %s\n' "$cache_home"
