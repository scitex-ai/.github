"""The org profile README is a deliverable with a checklist, so it gets tests.

WHY THIS FILE EXISTS. `profile/README.md` renders at github.com/scitex-ai, the
one page a researcher sees before deciding whether SciTeX is worth an afternoon.
It is also the only file in this repo that no workflow, import or build consumes
— every other file here is load-bearing for CI and breaks loudly when edited
wrongly. This one breaks quietly, and the failure it has already had once is
worse than a typo: it *described the organisation in terms the organisation
could not support*. So the assertions below are the checklist, as structure.

WHAT IS PINNED, AND WHY EACH ONE:

  * EN/JA entry points exist and link to each other. The operator works in
    Japanese and most of the ecosystem's prose is English; a reader who lands
    on one and cannot find the other is stuck on the profile page.
  * A relative asset that is referenced but absent is a broken image on the
    profile page, which is the worst kind of defect there: invisible in review,
    visible to every visitor. Checked through the SAME resolver the standalone
    link checker uses, so the two cannot drift into disagreeing about what
    "resolves" means.
  * The proof image is labelled as a DEVELOPMENT build, in both languages, near
    the image. The composite in `profile/assets/` is cropped from real
    development-build screenshots and real committed artifacts; publishing it
    without that label would be the exact overclaim this repo forbids.
  * The maturity table is dated. Its numbers (followers, zero-star repos, the
    concentration of stars) go stale within weeks, and an undated measurement
    presented as current is how a profile starts lying again.
  * No adoption claims. A young project's profile is under constant pressure to
    imply traction it does not have, and invented numbers are the failure mode
    with the highest cost here. Measured facts about the organisation's own
    size are fine — "6 followers" is evidence of youth, not a claim of
    adoption — so the patterns below target *positive* use-claims only.
  * Assets stay small. The profile page is the first thing a phone loads; a
    multi-megabyte PNG committed "just for the README" is a real cost paid by
    every visitor, and it is invisible in review.

File-only — parses markdown, stats files, resolves paths. No network, no gh,
cannot flake. The network half of the link checking is
`scripts/check_profile_links.py`, run by `profile-link-check.yml`, and is
deliberately NOT duplicated here.

Mutation-checked, every one of these verified to turn at least one test red:
deleting BOTH copies of the JA switch, pointing an asset at a missing file,
relabelling the proof as production screenshots, adding "trusted by 12,000
researchers", removing the measurement date while leaving the table's other
dates in place, deleting one asset's manifest row, committing a 5 MB PNG.

TWO OF THOSE MUTATIONS PASSED FIRST TIME, and the fixes are the checks above.
Deleting the language switch in the header left the same link in the footer, so
the file still linked both languages — hence "no second copy" is now stated
explicitly. And the date check accepted the ORG'S CREATION DATE (`2025-05-11`),
a real date in a real table, which is not a measurement date — hence the
pattern matches the claim ("Measured <date>") rather than any date nearby.
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[1]
_PROFILE = _REPO / "profile"
_ASSETS = _PROFILE / "assets"
_MANIFEST = _ASSETS / "ASSET-MANIFEST.md"
_LINK_CHECKER = _REPO / "scripts" / "check_profile_links.py"

_READMES = {"en": _PROFILE / "README.md", "ja": _PROFILE / "README.ja.md"}

#: The JA page is a TRANSLATION, so the checks below cannot demand English
#: keywords — a test that looks for "development build" in Japanese prose would
#: force the translation to be half English, which is the opposite of an entry
#: point. Each check therefore carries the tokens that ARE the claim in that
#: language; a language without an entry is a claim that cannot be made there.
_DEV_BUILD_LABEL = {"en": ("development",), "ja": ("開発", "development")}
_HOSTED_SELF_HOSTED = {"en": ("hosted", "self-host"), "ja": ("ホステッド", "セルフホスト")}
_ALPHA_LABEL = {"en": ("alpha",), "ja": ("アルファ", "alpha")}
_MEASURED_HEADING = {"en": "where this actually is", "ja": "いま実際どこにあるのか"}
#: The measurement CLAIM, not just any date: the maturity table legitimately
#: carries other dates (the org's creation date), so a bare \d{4}-\d{2}-\d{2}
#: search passes on the wrong one.
_MEASURED_CLAIM = {"en": r"measured\s+(\d{4}-\d{2}-\d{2})", "ja": r"(\d{4}-\d{2}-\d{2})\s*時点"}

#: Per-asset ceiling. phone-first: the whole page is ~450 KB today, and this
#: budget exists to stop one asset from dwarfing it.
_ASSET_BUDGET_BYTES = 250_000
_TOTAL_ASSET_BUDGET_BYTES = 400_000

#: Positive adoption/use claims. Deliberately NOT matching bare counts: "6
#: followers", "59 with zero stars" and "121 of them (71%) on two repos" are
#: measurements of this organisation's own smallness, which the maturity
#: section is REQUIRED to state.
_ADOPTION_CLAIMS = (
    r"\b(?:used|trusted|adopted|chosen)\s+by\b",
    r"\b\d[\d,\.]*\s*(?:\+)?\s*(?:users|researchers|organisations|organizations|labs|institutions|downloads|installs)\b",
    r"\b\d[\d,\.]*\s*stars\b",
    r"\b(?:widely used|industry[- ]leading|thousands of|millions of|de facto)\b",
    r"\bproduction[- ]ready\b",
)


def _readme(lang: str) -> str:
    return _READMES[lang].read_text(encoding="utf-8")


def _link_checker():
    """Load the standalone checker so both use ONE definition of resolution."""
    spec = importlib.util.spec_from_file_location("_check_profile_links", _LINK_CHECKER)
    assert spec is not None and spec.loader is not None, _LINK_CHECKER
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def checker():
    return _link_checker()


# ---------------------------------------------------------------------------
# EN/JA entry points. A reader who lands on one must be able to reach the other.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("lang", sorted(_READMES))
def test_the_readme_exists(lang: str) -> None:
    # Arrange
    path = _READMES[lang]
    # Act
    exists = path.exists()
    # Assert
    assert exists, f"{path.relative_to(_REPO)} is missing"


@pytest.mark.parametrize("lang", sorted(_READMES))
def test_the_readme_offers_both_languages(lang: str) -> None:
    """A language switch, not just a footnote — it must link the OTHER file."""
    # Arrange
    other = [p.name for code, p in _READMES.items() if code != lang][0]
    text = _readme(lang)
    # Act — either markdown ``[x](target)`` or the profile's HTML switch
    linked = f"({other})" in text or f'"{other}"' in text
    # Assert
    assert linked, f"{_READMES[lang].name} does not link {other}"


# ---------------------------------------------------------------------------
# Every relative reference resolves, AS THE PROFILE PAGE RESOLVES IT: relative
# to the README's own directory. Measured through the shipped checker.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("lang", sorted(_READMES))
def test_every_relative_target_exists(lang: str, checker) -> None:
    # Arrange
    readme = _READMES[lang]
    relative = [t for t in checker.targets(readme) if not t.startswith("http")]
    # Act
    missing = [t for t in relative if not checker.check_relative(readme, t)[0]]
    # Assert
    assert missing == [], f"{readme.name} points at nothing: {missing}"


def test_the_proof_image_is_referenced_by_both_readmes() -> None:
    """Guards the two tests below: an unreferenced image costs weight for nothing."""
    # Arrange
    proof = "assets/proof-e2e.jpg"
    # Act
    referenced = {lang: proof in _readme(lang) for lang in _READMES}
    # Assert
    assert all(referenced.values()), referenced


def test_the_proof_image_has_alt_text() -> None:
    """A profile image with empty alt text is a blank line for a screen reader."""
    # Arrange
    pattern = re.compile(r'<img[^>]*src="assets/proof-e2e\.jpg"[^>]*alt="([^"]*)"')
    # Act
    alts = {lang: pattern.search(_readme(lang)) for lang in _READMES}
    # Assert
    for lang, match in alts.items():
        assert match, f"{lang}: no <img> tag with alt for proof-e2e.jpg"
        assert len(match.group(1)) >= 40, f"{lang}: alt text too short to be useful"


# ---------------------------------------------------------------------------
# Honest labelling. The composite IS a development build; saying so is not
# optional, and it must be said next to the image, in both languages.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("lang", sorted(_READMES))
def test_the_proof_is_labelled_a_development_build(lang: str) -> None:
    # Arrange
    text = _readme(lang)
    image_at = text.index("assets/proof-e2e.jpg")
    # Act: the label lives in the ~2000 characters that follow the image
    vicinity = text[image_at : image_at + 2000].lower()
    # Assert
    assert any(token in vicinity for token in _DEV_BUILD_LABEL[lang]), (
        f"{_READMES[lang].name}: the proof image is not labelled as a development "
        "build near the image — see the manifest for what that label covers"
    )


@pytest.mark.parametrize("lang", sorted(_READMES))
def test_the_maturity_numbers_are_dated(lang: str) -> None:
    """Undated measurements presented as current are how a profile starts lying."""
    # Arrange
    text = _readme(lang)
    header_at = text.lower().index(_MEASURED_HEADING[lang])
    # Act
    section = text[header_at : header_at + 1200]
    # Assert
    assert re.search(_MEASURED_CLAIM[lang], section, flags=re.IGNORECASE), (
        f"{_READMES[lang].name}: the maturity section states numbers with no "
        "measurement date; they go stale in weeks"
    )


@pytest.mark.parametrize("lang", sorted(_READMES))
def test_the_maturity_section_admits_small_numbers(lang: str) -> None:
    """The section exists to state the unflattering measurements, so pin one.

    Zero-star repos and the concentration of stars are the two facts a growth
    document is most tempted to omit; both are also the reason the page tells a
    reader to adopt ONE package rather than the organisation.
    """
    # Arrange
    text = _readme(lang)
    # Act
    zero_star = re.search(r"(zero stars|スター\s*0)", text)
    concentration = re.search(r"(71%|71\s*%)", text)
    # Assert
    assert zero_star, f"{_READMES[lang].name}: no zero-star count"
    assert concentration, f"{_READMES[lang].name}: no star-concentration figure"


@pytest.mark.parametrize("lang", sorted(_READMES))
@pytest.mark.parametrize("claim", _ADOPTION_CLAIMS)
def test_no_adoption_claims(lang: str, claim: str) -> None:
    # Arrange
    text = _readme(lang)
    # Act
    found = re.findall(claim, text, flags=re.IGNORECASE)
    # Assert
    assert found == [], (
        f"{_READMES[lang].name} claims adoption ({found!r}). Measured facts about "
        "this organisation's own size are allowed and required; claims about who "
        "uses it are not, because nobody has measured them."
    )


# ---------------------------------------------------------------------------
# The 60-second path is a promise about a command, and commands rot.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("lang", sorted(_READMES))
def test_the_start_path_states_the_install_command(lang: str) -> None:
    # Arrange
    text = _readme(lang)
    # Act
    present = "uv pip install scitex" in text
    # Assert
    assert present, f"{_READMES[lang].name} has no runnable install command"


def test_the_start_path_shows_a_measured_duration() -> None:
    """The heading says sixty seconds; the file has to say where that came from."""
    # Arrange
    text = _readme("en")
    # Act
    seconds = re.search(r"≈\s*(\d+)\s*s\b", text)
    # Assert
    assert seconds, "the install command carries no measured duration"
    assert int(seconds.group(1)) <= 60, (
        "the 60-second section promises a number it does not meet; either fix the "
        "measurement or stop calling it sixty seconds"
    )


# ---------------------------------------------------------------------------
# The required sections. Each one is a question a first-time researcher has.
# ---------------------------------------------------------------------------


_REQUIRED_LINKS = {
    "flagship umbrella package": "https://github.com/scitex-ai/scitex-python",
    "the discussion venue": "https://github.com/scitex-ai/scitex-python/discussions",
    "the CLA": "https://github.com/scitex-ai/scitex-python/blob/main/CLA.md",
    "the hosted instance": "https://scitex.ai",
    "the self-hosted entry point": "https://github.com/scitex-ai/scitex-hub",
    "the end-to-end demo": "https://github.com/scitex-ai/automated-research-demo",
    "all repositories": "https://github.com/orgs/scitex-ai/repositories",
}


@pytest.mark.parametrize("lang", sorted(_READMES))
@pytest.mark.parametrize(("what", "url"), sorted(_REQUIRED_LINKS.items()))
def test_the_required_way_out_is_linked(lang: str, what: str, url: str) -> None:
    # Arrange
    text = _readme(lang)
    # Act
    present = url in text
    # Assert
    assert present, f"{_READMES[lang].name} does not link {what} ({url})"


@pytest.mark.parametrize("lang", sorted(_READMES))
def test_the_hosted_and_self_hosted_choice_is_stated(lang: str) -> None:
    """Both halves, and the alpha warning on the hosted half, must be present."""
    # Arrange
    text = _readme(lang).lower()
    tokens = _HOSTED_SELF_HOSTED[lang]
    # Act
    both = all(token in text for token in tokens)
    warned = any(token in text for token in _ALPHA_LABEL[lang])
    # Assert
    assert both, (
        f"{_READMES[lang].name} does not present both halves of the "
        f"hosted/self-hosted choice (looked for {tokens})"
    )
    assert warned, (
        f"{_READMES[lang].name} offers the hosted hub without saying it is alpha "
        f"(looked for {_ALPHA_LABEL[lang]})"
    )


# ---------------------------------------------------------------------------
# Weight and provenance.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "asset", sorted(p.name for pattern in ("*.png", "*.jpg") for p in _ASSETS.glob(pattern))
)
def test_each_asset_is_within_budget(asset: str) -> None:
    # Arrange
    path = _ASSETS / asset
    # Act
    size = path.stat().st_size
    # Assert
    assert size <= _ASSET_BUDGET_BYTES, (
        f"{asset} is {size / 1000:.0f} KB; the profile page is the first thing a "
        "phone loads. Optimise it (see scripts/build_profile_proof.py for the "
        "posterise/palette approach) or move it out of the README's path."
    )


def test_the_assets_together_fit_the_page_budget() -> None:
    # Arrange
    pngs = sorted(p for pattern in ("*.png", "*.jpg") for p in _ASSETS.glob(pattern))
    # Act
    total = sum(p.stat().st_size for p in pngs)
    # Assert
    assert total <= _TOTAL_ASSET_BUDGET_BYTES, (
        f"{total / 1000:.0f} KB of images on one profile page (budget "
        f"{_TOTAL_ASSET_BUDGET_BYTES / 1000:.0f} KB)"
    )


def test_the_manifest_is_present_and_names_every_asset() -> None:
    """An asset with no recorded source is an asset nobody can review."""
    # Arrange
    manifest = _MANIFEST.read_text(encoding="utf-8")
    assets = sorted(p.name for p in _ASSETS.iterdir() if p.is_file() and p.name != _MANIFEST.name)
    # Act
    unrecorded = [a for a in assets if a not in manifest]
    # Assert
    assert unrecorded == [], f"not recorded in ASSET-MANIFEST.md: {unrecorded}"


def test_the_manifest_records_where_the_composite_came_from() -> None:
    """The composite is crops of real screenshots; the manifest must say which
    build, which commit and what was redacted, or it is just an assertion."""
    # Arrange
    manifest = _MANIFEST.read_text(encoding="utf-8")
    required = ("commit", "sha256", "crop", "cropped", "development")
    # Act
    missing = [token for token in required if token not in manifest.lower()]
    # Assert
    assert missing == [], f"ASSET-MANIFEST.md does not record: {missing}"
