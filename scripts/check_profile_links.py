#!/usr/bin/env python3
"""Check every link and image the org profile READMEs depend on.

WHY THIS EXISTS. `profile/README.md` renders at github.com/scitex-ai — the one
page a researcher sees before deciding whether SciTeX is worth an afternoon. It
is also the one page in this repo whose *content* is other repositories, other
sites and other images, so nothing in the ordinary CI here touches it: no test
imports it, no build consumes it. It rots silently. The badges are worse than
the links, because a broken shields.io badge renders as a broken-image icon at
the top of the page while returning HTTP 200 to a naive check.

WHAT IT CHECKS, in two classes, because they fail differently:

  1. RELATIVE targets (``assets/proof-e2e.png``, ``README.ja.md``). GitHub
     resolves these against the *file's* directory, so a path that does not
     exist in this repo is a broken image on the org page. Checked against the
     filesystem — no network, cannot flake.
  2. ABSOLUTE https targets. One HTTP request each, following redirects, with
     a timeout. A non-2xx/3xx is a failure, and so is plain ``http://``: a
     public research page served over http is a downgrade a reader notices.

The two vulnerability classes the org actually has are both covered: a URL
whose target was renamed/transferred (repos move, e.g. every
``ywatanabe1989/...`` link in this ecosystem is one transfer away from 404),
and a relative path that only exists on the author's machine.

TWO THINGS THAT WOULD OTHERWISE MAKE THIS CHECK LIE, both handled explicitly:

  * TRANSIENT FAILURES. A TLS handshake timeout on github.com is not a broken
    link, and a weekly job that goes red for one is a job people learn to
    ignore. Every absolute target is retried (``--retries``, default 2) before
    it is reported.
  * THIS REPO'S OWN FILES. A README may legitimately link a script that the
    very branch being checked adds, so ``blob/main/<path>`` 404s until the PR
    merges. When the URL names a path in THIS repository on the default branch
    and that path exists in the working tree, the local tree is the authority
    and the failure is reported as ``pending merge``. A typo still fails,
    because a typo'd path is not in the tree either.

Usage:
    python scripts/check_profile_links.py            # both classes
    python scripts/check_profile_links.py --offline  # class 1 only
    python scripts/check_profile_links.py --json
Exit code: 0 when everything resolves, 1 otherwise.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
_PROFILE = _REPO / "profile"
_READMES = ("README.md", "README.ja.md")

#: Markdown ``[text](target)`` and HTML ``src="target"`` / ``href="target"``.
#: Anchors (``#section``) are not links to anywhere in this context, and mailto:
#: is not fetchable — both are skipped rather than reported as failures.
_MD_LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
_HTML_ATTR = re.compile(r'(?:src|href)="([^"]+)"')

_TIMEOUT = 25
_UA = "scitex-ai-profile-link-check/1.0 (+https://github.com/scitex-ai/.github)"

#: This repository's own identity ON GITHUB. Not derived from the checkout's
#: directory name, which is free to differ (and does: the working copy of
#: scitex-ai/.github is commonly a task-named folder).
_SELF_OWNER = "scitex-ai"
_SELF_REPO = ".github"

#: A link to one of this repo's own files on the default branch.
_SELF_BLOB = re.compile(r"^https://github\.com/([^/]+)/([^/]+)/blob/([^/]+)/(.+)$")


def targets(readme: Path) -> list[str]:
    text = readme.read_text(encoding="utf-8")
    found = _MD_LINK.findall(text) + _HTML_ATTR.findall(text)
    return sorted({t for t in found if not t.startswith(("#", "mailto:"))})


def check_relative(readme: Path, target: str) -> tuple[bool, str]:
    """Relative targets resolve from the README's own directory (GitHub's rule)."""
    path = (readme.parent / target).resolve()
    inside_repo = _REPO in path.parents or path == _REPO
    if not inside_repo:
        return False, f"resolves outside the repo: {path}"
    if not path.exists():
        return False, f"missing on disk: {path.relative_to(_REPO)}"
    return True, str(path.relative_to(_REPO))


def _owns_that_path(target: str) -> bool:
    """True when ``target`` is a ``blob/<branch>/<path>`` link into this repo's
    own working tree — i.e. a file this branch may be the one adding."""
    match = _SELF_BLOB.match(target)
    if not match:
        return False
    owner, repo, _branch, path = match.groups()
    if (owner, repo) != (_SELF_OWNER, _SELF_REPO):
        return False
    return (_REPO / path).exists()


def check_absolute(target: str, retries: int = 2) -> tuple[bool, str]:
    if target.startswith("http://"):
        return False, "plain http:// — use https://"
    if not target.startswith("https://"):
        return False, "not an absolute https URL"

    last = ""
    for attempt in range(retries + 1):
        request = urllib.request.Request(target, method="GET", headers={"User-Agent": _UA})
        try:
            with urllib.request.urlopen(request, timeout=_TIMEOUT) as response:
                body = response.read(2048)
                status = response.status
            break
        except urllib.error.HTTPError as exc:
            last = f"HTTP {exc.code}"
            if exc.code == 404 and _owns_that_path(target):
                return True, "HTTP 404 on the default branch, but the path exists in this tree (pending merge)"
            if exc.code < 500:  # a 4xx that is not ours will not heal on retry
                return False, last
        except Exception as exc:  # DNS, TLS, timeout — retryable
            last = f"{type(exc).__name__}: {exc}"
        if attempt < retries:
            time.sleep(1.5 * (attempt + 1))
    else:
        return False, last

    if not 200 <= status < 400:
        return False, f"HTTP {status}"
    # A badge that 200s but whose body is not an image still renders broken on
    # the profile page, which is the failure this check was written after.
    ctype = response.headers.get_content_type()
    if status == 200 and target.startswith("https://img.shields.io") and not ctype.startswith(
        "image/"
    ):
        return False, f"shields.io returned {ctype}, not an image"
    return True, f"HTTP {status} ({len(body)} B read)"


def collect(retries: int = 2) -> list[dict]:
    results: list[dict] = []
    for name in _READMES:
        readme = _PROFILE / name
        if not readme.exists():
            continue
        for target in targets(readme):
            relative = not target.lower().startswith(("http://", "https://"))
            try:
                ok, detail = (
                    check_relative(readme, target) if relative else check_absolute(target, retries)
                )
            except Exception as exc:  # never let one target abort the run
                ok, detail = False, f"{type(exc).__name__}: {exc}"
            results.append(
                {
                    "readme": name,
                    "target": target,
                    "kind": "relative" if relative else "absolute",
                    "ok": ok,
                    "detail": detail,
                }
            )
    return results


def main() -> int:
    summary = (__doc__ or "").strip().splitlines()[0]
    parser = argparse.ArgumentParser(description=summary)
    parser.add_argument("--offline", action="store_true", help="check relative targets only")
    parser.add_argument("--json", action="store_true", help="emit JSON")
    parser.add_argument("--retries", type=int, default=2, help="retries per absolute target")
    args = parser.parse_args()

    results = collect(retries=args.retries)
    if args.offline:
        results = [r for r in results if r["kind"] == "relative"]

    failures = [r for r in results if not r["ok"]]

    if args.json:
        print(json.dumps({"checked": len(results), "failures": failures}, indent=2))
    else:
        for r in results:
            mark = "ok  " if r["ok"] else "FAIL"
            print(f"{mark} {r['readme']:>13}  {r['target']}\n         {r['detail']}")
        print(f"\n{len(results) - len(failures)}/{len(results)} targets resolve")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
