# Asset manifest — `profile/assets/`

Every image in this directory is either the organisation's own logo or a crop of
something that already exists and can be checked. There are **no mockups, no
redrawn UI, no synthesised figures, and no production screenshot passed off as a
development one** anywhere in this directory. If that changes, this file is the
first thing a reviewer should read, so it records the source, the commit, the
date and the redactions of each asset rather than describing the result in
prose.

Legend: **dev** = captured from a development build of SciTeX Hub on
`127.0.0.1:8000`, signed in as a throwaway demo account. Not production.

## `proof-e2e.png`

Built by [`scripts/build_profile_proof.py`](../../scripts/build_profile_proof.py);
900 × 1757 px, palette PNG. Four vertically stacked crops, numbered ①–④ in the
image, in the order a project actually moves: files → manuscript → literature →
figures.

| # | Crop shows | Source | Source commit / date | sha256 (source) |
|---|---|---|---|---|
| ① | A project's file listing: `data/`, `figures/`, `references.bib` beside the manuscript | `scitex-hub:media/videos/demos/projects-2026-09-14-thumbnail.png` — a frame of the Hub's own narrated how-to recording, scenario `scripts/demo_videos/scenarios/projects.yaml` | hub `b98644f3be708f81b422c5831c6419f6524cc976`; frame dated 2026-09-14 22:22, recording pipeline landed in `39622a76a` (2026-09-15) | `d3d77e6a7387ca9f8e398c11880b9f79f09282f256b045c354309a897bf56e1f` |
| ② | Writer: LaTeX source, compiled PDF preview, and the `pdflatex` log ending in "*Preview compilation completed successfully*" | `scitex-hub:media/videos/demos/writer-2026-09-14-thumbnail.png` — frame of the same recording, scenario `scripts/demo_videos/scenarios/writer.yaml` | as above; frame dated 2026-09-14 22:25 | `450e08f26da0cccc071696cc8f6f76a5ac30d760ef55ea10236a231e6aba98f9` |
| ③ | Scholar: a populated library — real titles, years, reading states, DOI and abstract in the detail pane | `scitex-hub:docs/images/screenshot-scholar.png` (tracked in the Hub repo, where it illustrates the Hub's own README) | hub `71f73fc8af6eebee30ffa12e46c339e8d8ae921f` (2026-03-08); file mtime 2026-08-16 | `4e8315247c12615023c76970f64d08fc493ae42395c60691fe7e421a67457b48` |
| ④ | Figures 1–2 as compiled into the manuscript PDF of a real run: bar plots, and the age × sleep interaction for memory (*p* < .001) | `automated-research-demo:scitex/writer/paper/01_manuscript/manuscript.pdf`, page 19, rendered at 140 dpi | `0cc38083d7d247e0f01832d5f4c3ef890c1edcc7` (2026-01-20) | fetched at build time |

Both Hub frames are **dev**, from the throwaway demo account `howto-demo-0914`
(created 2026-09-14 for the recording and used for nothing else). The Scholar
panel is **dev** as well, from an earlier session on the same instance.

### Redactions

Identifiers were **cropped away**, wherever the crop rectangle could simply be
moved to exclude them. Nothing was blurred, and nothing was retouched to look
better than it is:

| Cropped out | Applies to |
|---|---|
| Browser chrome — tab titles, address bar (`127.0.0.1:8000`), bookmarks, extension icons | ③ (the source is a full-window capture); ① and ② are recording frames and carry no chrome |
| Account and project names — the breadcrumb `owner / project` row | ① |
| The file tree and console rail showing `user/project` and a shell prompt | ③ |
| Account avatar, notification and mail badges, project selector | ① ② ③ |
| The recording's tutorial callouts ("*The repository view lists every file…*", "*The PDF of your section appears…*") | ① ② — painted out with each panel's own background colour, **sampled at run time**, not hardcoded |

Not redacted, deliberately: the demo project's own content (file names, the
one-line project description, the paper titles in ③, commit hash `b84fa30` of
the demo repository) and the compile log in ②, including a `preview.sty not
found` warning. That warning is part of what a development build prints, and
the panel is labelled as a development build; removing it would be the kind of
tidying this manifest exists to prevent.

### What the composite does NOT claim

- Not production. Not a stable release. The Hub is alpha.
- No user counts, adoption numbers or performance claims appear in it.
- ④ is the *demo repository's* committed output, produced by an agent run
  described in that repository; its N=180 results are a synthetic-data
  demonstration, not a scientific finding.

## `scitex-logo.png`, `scitex-icon.png`

The organisation's own logo and icon, palette-optimised **in place**: same
pixels' dimensions (3001 × 888 and 512 × 512), same filenames, so any existing
hotlink keeps working. Only the PNG colour depth changed, because the two files
were 305 KB and 71 KB being displayed at 360 px and 40 px wide.

| file | before | after | dimensions |
|---|---|---|---|
| `scitex-logo.png` | 304 953 B | 85 745 B | 3001 × 888, unchanged |
| `scitex-icon.png` | 71 479 B | 8 348 B | 512 × 512, unchanged |

Maximum per-channel difference is 17 on 0.10 % of pixels (measured against the
originals); no dimension or filename changed.
