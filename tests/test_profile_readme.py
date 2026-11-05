"""File-only contracts for the current, bilingual organisation profile.

Keep truthful maturity/data labels, source provenance, useful exits, local-link
integrity and the original image budgets. Historical composites remain available
for stable hotlinks; they must not masquerade as the current five captures.
Negative controls exercise the same predicates without changing repository files.
Network/GitHub rendering checks remain the owning link checker's separate scope.
"""

from __future__ import annotations

import hashlib
import importlib.util
import re
from html.parser import HTMLParser
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[1]
_PROFILE = _REPO / "profile"
_ASSETS = _PROFILE / "assets"
_MANIFEST = _ASSETS / "ASSET-MANIFEST.md"
_LINK_CHECKER = _REPO / "scripts" / "check_profile_links.py"
_READMES = {"en": _PROFILE / "README.md", "ja": _PROFILE / "README.ja.md"}
_SCREENSHOTS = {
    "figrecipe-20261103-scene-768.webp": "FigRecipe",
    "writer-20261102-768.webp": "Writer",
    "hub-20261102-768.webp": "Hub",
    "scholar-20261102-768.webp": "Scholar",
    "cards-board-mnist-20261103-768.webp": "Cards",
}
_FEATURED = tuple(_SCREENSHOTS)[:2]
_BRANDING = {"scitex-logo.png", "scitex-icon.png"}
_DEV_BUILD_LABEL = {"en": ("development",), "ja": ("開発", "development")}
_SYNTHETIC_LABEL = {"en": ("synthetic",), "ja": ("合成", "synthetic")}
_HOSTED_SELF_HOSTED = {
    "en": ("hosted", "self-host"),
    "ja": ("ホステッド", "セルフホスト"),
}
_ALPHA_LABEL = {"en": ("alpha",), "ja": ("アルファ", "alpha")}
_ASSET_BUDGET_BYTES = 250_000
_TOTAL_ASSET_BUDGET_BYTES = 400_000
_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}

_ADOPTION_CLAIMS = (
    r"\b(?:used|trusted|adopted|chosen)\s+by\b",
    r"\b\d[\d,\.]*\s*(?:\+)?\s*(?:users|researchers|organisations|organizations|labs|institutions|downloads|installs)\b",
    r"\b\d[\d,\.]*\s*stars\b",
    r"\b(?:widely used|industry[- ]leading|thousands of|millions of|de facto)\b",
    r"\bproduction[- ]ready\b",
    r"\d[\d,]*\s*(?:万人|人)\s*(?:が利用|のユーザー|の研究者)",
    r"本番(?:環境)?(?:対応済み|運用可能|運用に対応)",
)
_STALE_CLAIMS = (
    r"\b\d[\d,]*\s+(?:public\s+)?(?:repositories|repos|packages|followers|members|releases|threads)\b",
    r"(?:公開\s*)?\d[\d,]*\s*(?:リポジトリ|パッケージ|フォロワー|公開メンバー|スター|リリース)",
    r"\b(?:sixty|\d+)\s*[- ]?\s*seconds?\b",
    r"\d+\s*秒",
    r"≈\s*\d+\s*s\b",
    r"(?<![\w/])v?\d+\.\d+\.\d+(?:[-+][\w.]+)?",
)
_REQUIRED_LINKS = {
    "flagship umbrella package": "https://github.com/scitex-ai/scitex-python",
    "the discussion venue": "https://github.com/scitex-ai/scitex-python/discussions",
    "the CLA": "https://github.com/scitex-ai/scitex-python/blob/main/CLA.md",
    "the hosted instance": "https://scitex.ai",
    "the self-hosted entry point": "https://github.com/scitex-ai/scitex-hub",
    "the end-to-end demo": "https://github.com/scitex-ai/automated-research-demo",
    "all repositories": "https://github.com/orgs/scitex-ai/repositories",
}


class _ProfileHTML(HTMLParser):
    """Track actual img attributes and collapsible/featured grouping."""

    def __init__(self, text):
        super().__init__()
        self.images = []
        self.details = {}
        self._details = []
        self._paragraph = None
        self._next_group = 0
        self.visible = []
        self._offsets = [0]
        for line in text.splitlines(keepends=True):
            self._offsets.append(self._offsets[-1] + len(line))
        self.feed(text)

    def _position(self):
        line, column = self.getpos()
        return self._offsets[line - 1] + column

    def handle_starttag(self, tag, attrs):
        at = self._position()
        if tag == "details":
            self._next_group += 1
            self._details.append(self._next_group)
            self.details[self._next_group] = [at, None]
        if tag == "p":
            self._paragraph = at
        if tag == "img":
            self.images.append(
                {
                    **dict(attrs),
                    "at": at,
                    "paragraph": self._paragraph,
                    "details": self._details[-1] if self._details else None,
                }
            )

    def handle_endtag(self, tag):
        if tag == "details" and self._details:
            self.details[self._details.pop()][1] = self._position()
        if tag == "p":
            self._paragraph = None

    def handle_data(self, data):
        self.visible.append(data)


def _visible(text):
    return " ".join(_ProfileHTML(text).visible).lower()


def _image_problems(text, lang):
    parsed = _ProfileHTML(text)
    images = [
        i
        for i in parsed.images
        if i.get("src", "").startswith("assets/")
        and Path(i["src"]).name not in _BRANDING
    ]
    names = [Path(i["src"]).name for i in images]
    problems = []
    if sorted(names) != sorted(_SCREENSHOTS):
        problems.append(
            "current screenshot set differs (missing, duplicate or historical image)"
        )
    featured = [i for i in images if Path(i["src"]).name in _FEATURED]
    if (
        len(featured) != 2
        or any(i["details"] is not None for i in featured)
        or featured[0]["paragraph"] is None
        or len({i["paragraph"] for i in featured}) != 1
        or [Path(i["src"]).name for i in featured] != list(_FEATURED)
    ):
        problems.append(
            "featured FigRecipe/Writer must share a visible sibling paragraph"
        )
    for image in images:
        name = Path(image["src"]).name
        if name not in _SCREENSHOTS:
            continue
        alt = image.get("alt", "").strip()
        if len(alt) < 40 or _SCREENSHOTS[name].lower() not in alt.lower():
            problems.append(f"{name}: missing useful app-specific alt text")
        detail = image["details"]
        if name not in _FEATURED and detail is None:
            problems.append(f"{name}: secondary screenshot is not inside details")
        if detail is not None:
            start, end = parsed.details[detail]
            vicinity = _visible(text[start:end]) if end is not None else ""
        else:
            start = (
                image["paragraph"] if image["paragraph"] is not None else image["at"]
            )
            end = min(
                (span[0] for span in parsed.details.values() if span[0] > start),
                default=len(text),
            )
            vicinity = _visible(text[start:end])
        for kind, tokens in (
            ("development", _DEV_BUILD_LABEL[lang]),
            ("synthetic data", _SYNTHETIC_LABEL[lang]),
        ):
            if not any(token in vicinity for token in tokens):
                problems.append(
                    f"{name}: visible {kind} label missing near image group"
                )
    return problems


def _claim_problems(text):
    visible = _visible(text)
    return [
        pattern
        for pattern in (*_ADOPTION_CLAIMS, *_STALE_CLAIMS)
        if re.search(pattern, visible, re.IGNORECASE)
    ]


def _asset_paths(directory):
    return sorted(
        p
        for p in directory.iterdir()
        if p.is_file() and p.suffix.lower() in _IMAGE_SUFFIXES
    )


def _budget_problems(directory):
    assets = _asset_paths(directory)
    problems = [
        f"asset:{p.name}" for p in assets if p.stat().st_size > _ASSET_BUDGET_BYTES
    ]
    if sum(p.stat().st_size for p in assets) > _TOTAL_ASSET_BUDGET_BYTES:
        problems.append("total")
    return problems


def _manifest_problems(manifest, directory):
    problems = []
    if "source manifest:" not in manifest.lower() or "scitex-hub:" not in manifest:
        problems.append("source manifest location missing")
    for name in _SCREENSHOTS:
        rows = [
            line
            for line in manifest.splitlines()
            if line.startswith("|") and f"`{name}`" in line
        ]
        path = directory / name
        if len(rows) != 1 or not path.is_file() or path.is_symlink():
            problems.append(f"{name}: unique record/regular file missing")
            continue
        row = rows[0]
        cells = [cell.strip().strip("`") for cell in row.split("|")]
        if hashlib.sha256(path.read_bytes()).hexdigest() not in cells:
            problems.append(f"{name}: bytes do not match manifest SHA256")
        if str(path.stat().st_size) not in cells:
            problems.append(f"{name}: byte count missing")
        if not re.search(r"\b\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ\b", row):
            problems.append(f"{name}: capture UTC missing")
        if not re.search(r"(?<![0-9a-f])[0-9a-f]{40}(?![0-9a-f])", row):
            problems.append(f"{name}: observed source checkout missing")
    return problems


@pytest.fixture(scope="module")
def checker():
    spec = importlib.util.spec_from_file_location("_check_profile_links", _LINK_CHECKER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("lang", sorted(_READMES))
def test_bilingual_entrypoints_and_relative_targets(lang, checker):
    # Arrange
    readme = _READMES[lang]
    other = next(p.name for code, p in _READMES.items() if code != lang)
    # Act
    targets = checker.targets(readme)
    missing = [
        t
        for t in targets
        if not t.startswith("http") and not checker.check_relative(readme, t)[0]
    ]
    # Assert
    assert (readme.is_file(), other in targets, missing) == (True, True, [])


@pytest.mark.parametrize("lang", sorted(_READMES))
def test_current_screenshots_layout_alts_and_visible_labels(lang):
    # Arrange
    text = _READMES[lang].read_text(encoding="utf-8")
    # Act
    problems = _image_problems(text, lang)
    # Assert
    assert problems == []


@pytest.mark.parametrize("lang", sorted(_READMES))
def test_profile_keeps_install_maturity_choices_and_no_unsupported_claims(lang):
    # Arrange
    text = _READMES[lang].read_text(encoding="utf-8")
    # Act
    lowered = text.lower()
    # Assert
    assert (
        "uv pip install scitex" in text,
        all(t in lowered for t in _HOSTED_SELF_HOSTED[lang]),
        any(t in lowered for t in _ALPHA_LABEL[lang]),
        _claim_problems(text),
    ) == (True, True, True, [])


@pytest.mark.parametrize("lang", sorted(_READMES))
@pytest.mark.parametrize(("what", "url"), sorted(_REQUIRED_LINKS.items()))
def test_required_external_exit_is_retained(lang, what, url):
    # Arrange
    text = _READMES[lang].read_text(encoding="utf-8")
    # Act
    present = url in text
    # Assert
    assert present, f"{lang}: missing {what} ({url})"


@pytest.mark.parametrize("asset", [p.name for p in _asset_paths(_ASSETS)])
def test_each_asset_including_webp_keeps_original_budget(asset):
    # Arrange
    path = _ASSETS / asset
    # Act
    size = path.stat().st_size
    # Assert
    assert size <= _ASSET_BUDGET_BYTES


def test_all_retained_and_current_assets_keep_original_total_budget():
    # Arrange
    assets = _ASSETS
    # Act
    problems = _budget_problems(assets)
    # Assert
    assert problems == []


def test_manifest_names_all_assets_and_binds_current_capture_bytes():
    # Arrange
    manifest = _MANIFEST.read_text(encoding="utf-8")
    assets = [
        p.name for p in _ASSETS.iterdir() if p.is_file() and p.name != _MANIFEST.name
    ]
    # Act
    missing = [name for name in assets if name not in manifest]
    # Assert
    assert (missing, _manifest_problems(manifest, _ASSETS)) == ([], [])


@pytest.mark.parametrize("lang", sorted(_READMES))
@pytest.mark.parametrize(
    "mutation", ["missing", "historical", "empty-alt", "hide-featured", "remove-labels"]
)
def test_image_contract_rejects_regressions_without_mutating_source(lang, mutation):
    # Arrange
    text = _READMES[lang].read_text(encoding="utf-8")
    name = _FEATURED[0]
    transformations = {
        "missing": lambda s: re.sub(
            r'<img\b[^>]*src="assets/' + re.escape(name) + r'"[^>]*>', "", s
        ),
        "historical": lambda s: s.replace(name, "proof-e2e.jpg"),
        "empty-alt": lambda s: re.sub(r'alt="[^"]*"', 'alt=""', s),
        "hide-featured": lambda s: "<details>" + s + "</details>",
        "remove-labels": lambda s: re.sub(
            r"development|synthetic|開発|合成", "", s, flags=re.IGNORECASE
        ),
    }
    # Act
    problems = _image_problems(transformations[mutation](text), lang)
    # Assert
    assert problems


@pytest.mark.parametrize(
    "claim",
    [
        "Trusted by 12,000 researchers.",
        "Production-ready research platform.",
        "75 public repositories; 6 followers.",
        "公開75リポジトリ、フォロワー6。",
        "Version 2.30.8.",
        "Install in sixty seconds.",
        "最初の実行は60秒。",
    ],
)
def test_claim_contract_rejects_adoption_static_stats_versions_and_speed_promises(
    claim,
):
    # Arrange
    text = "A truthful alpha profile.\n" + claim
    # Act
    problems = _claim_problems(text)
    # Assert
    assert problems


@pytest.mark.parametrize("field", ["row", "hash", "capture", "checkout", "source"])
def test_current_manifest_rejects_missing_or_tampered_provenance(field):
    # Arrange
    text = _MANIFEST.read_text(encoding="utf-8")
    name = _FEATURED[0]
    row = next(
        line
        for line in text.splitlines()
        if line.startswith("|") and f"`{name}`" in line
    )
    transforms = {
        "row": lambda s: s.replace(row, ""),
        "hash": lambda s: s.replace(
            hashlib.sha256((_ASSETS / name).read_bytes()).hexdigest(), "0" * 64
        ),
        "capture": lambda s: s.replace(
            row, re.sub(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", "unknown", row)
        ),
        "checkout": lambda s: s.replace(
            row, re.sub(r"(?<![0-9a-f])[0-9a-f]{40}(?![0-9a-f])", "unknown", row)
        ),
        "source": lambda s: s.replace(
            "Source manifest:", "Unknown provenance:"
        ).replace("scitex-hub:", "unknown:"),
    }
    # Act
    problems = _manifest_problems(transforms[field](text), _ASSETS)
    # Assert
    assert problems


@pytest.mark.parametrize(
    "sizes,expected", [([250_001], "asset:"), ([200_001, 200_000], "total")]
)
def test_webp_cannot_evade_per_asset_or_total_budget(tmp_path, sizes, expected):
    # Arrange
    for index, size in enumerate(sizes):
        (tmp_path / f"owned-{index}.WEBP").write_bytes(b"x" * size)
    # Act
    problems = _budget_problems(tmp_path)
    # Assert
    assert any(problem.startswith(expected) for problem in problems)


@pytest.mark.parametrize(
    "target", ["../../../outside.webp", "assets/missing-current.webp"]
)
def test_relative_resolver_still_refuses_outside_and_missing_targets(checker, target):
    # Arrange
    readme = _READMES["en"]
    # Act
    ok, _detail = checker.check_relative(readme, target)
    # Assert
    assert ok is False
