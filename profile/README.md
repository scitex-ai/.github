<p align="center">
  <a href="https://scitex.ai">
    <img src="assets/scitex-logo.png" alt="SciTeX" width="400">
  </a>
</p>

<p align="center"><b>Open-source platform for reproducible scientific research, from data to manuscript.</b></p>

<p align="center">
  <a href="https://scitex.ai">scitex.ai</a> &middot;
  <code>uv pip install scitex[all]</code> &middot;
  <a href="https://scitex.ai/demos/">Demos</a>
</p>

---

## What SciTeX does, in 30 seconds

SciTeX is a modular ecosystem of 70 open-source packages covering the full research
workflow: literature search, data analysis, statistics, figures, manuscript writing,
and AI-agent orchestration — all built around one idea: **every result should trace
back to the data and code that produced it.**

See it end-to-end: [**automated-research-demo**](https://github.com/scitex-ai/automated-research-demo)
— literature search → analysis → figures → manuscript → revision, run autonomously
from synthetic data to a peer-reviewable draft. Kept unmodified as a snapshot of what
the ecosystem could do at that point in time.

---

## Core components

| Component | Description | Repository |
|-----------|-------------|------------|
| **SciTeX-Python** | Modular Python toolkit for scientific research, 200+ MCP tools | [scitex-python](https://github.com/scitex-ai/scitex-python) |
| **SciTeX-Scholar** | Literature search, enrichment, download, and management | [scitex-scholar](https://github.com/scitex-ai/scitex-scholar) |
| **FigRecipe** | Reproducible matplotlib wrapper, mm-precision layouts, 47 plot types | [figrecipe](https://github.com/scitex-ai/figrecipe) |
| **SciTeX-Writer** | LaTeX manuscript compilation with automatic versioning and diffs | [scitex-writer](https://github.com/scitex-ai/scitex-writer) |
| **SciTeX-Hub** (live at [scitex.ai](https://scitex.ai)) | Self-hostable browser application for scientific research | [scitex-hub](https://github.com/scitex-ai/scitex-hub) |
| **SciTeX-Agent-Container** | Declarative framework for running AI coding-agent fleets | [scitex-agent-container](https://github.com/scitex-ai/scitex-agent-container) |

---

## Architecture — 6-layer dependency cascade (+ orthogonal platform peers)

```
                       ┌──────────────────────────┐
   L5 — umbrella       │   scitex   (re-export)   │
                       └────────────┬─────────────┘
                                    ▼
   ┌──────────────────────────────────────────────────────────────┐
   │  L4 — observers / UX            (depend ↓, never ↑)          │
   │  scitex-clew  scitex-audit  scitex-notification  scitex-audio│
   └────────────────────────────┬─────────────────────────────────┘
                                ▼
   ┌──────────────────────────────────────────────────────────────┐
   │  L3 — workflow producers        (apps + orchestrators)       │
   │  scitex-app · -browser · -genai · -ml · -notebook · -repro · │
   │  -scholar · -seizure-metrics · -session · -todo · -ui · -web │
   │  · -writer · socialia                                        │
   └────────────────────────────┬─────────────────────────────────┘
                                ▼
   ┌──────────────────────────────────────────────────────────────┐
   │  L2 — domain producers          (peer ⇄ peer optional)       │
   │  figrecipe ⇄ scitex-stats · scitex-plt · -pd · -nn · -dsp ·  │
   │  -cv · -linalg · -math · -tex · -msword · -benchmark ·       │
   │  -capture · -events · -git · -hpc · -template                │
   └────────────────────────────┬─────────────────────────────────┘
                                ▼
   ┌──────────────────────────────────────────────────────────────┐
   │  L1 — IO + data leaves          (no peer deps)               │
   │  scitex-io · -db · -dataset · -ssh                           │
   │  crossref-local · openalex-local                              │
   └────────────────────────────┬─────────────────────────────────┘
                                ▼
   ┌──────────────────────────────────────────────────────────────┐
   │  L0 — tooling leaves            (no peer deps; used by all)  │
   │  scitex-types · -path · -str · -dict · -logging · -etc ·     │
   │  -compat · -dev · -config · -core · -context · -datetime ·   │
   │  -decorators · -gists · -introspect · -os · -parallel        │
   │  · -repl · -resource · -sh                                   │
   └──────────────────────────────────────────────────────────────┘

   Orthogonal (orchestration / platform — not in the cascade):
     scitex-hub   scitex-orochi   scitex-agent-container
     scitex-container   newb
```

<details>
<summary><b>All packages — full table</b></summary>

Sourced from [`scitex_dev._ecosystem._registry.ECOSYSTEM`](https://github.com/scitex-ai/scitex-dev/blob/main/src/scitex_dev/_ecosystem/_registry.py)

| Package | scitex Module | Layer | Description |
|---------|---------------|-------|-------------|
| [scitex](https://github.com/scitex-ai/scitex-python) | — *(umbrella)* | L5 | Umbrella package — reproducible science from raw data to manuscript |
| [scitex-clew](https://github.com/scitex-ai/scitex-clew) | `scitex.clew` | L4 | Verifiable knowledge graph for scientific experiments |
| [scitex-notification](https://github.com/scitex-ai/scitex-notification) | `scitex.notification` | L4 | Multi-backend notification system |
| [scitex-audio](https://github.com/scitex-ai/scitex-audio) | `scitex.audio` | L4 | Text-to-Speech with multiple backends |
| [scitex-app](https://github.com/scitex-ai/scitex-app) | `scitex.app` | L3 | App SDK — write-once interface for local + cloud apps |
| [scitex-scholar](https://github.com/scitex-ai/scitex-scholar) | `scitex.scholar` | L3 | Scientific paper search, enrichment, download, management |
| [scitex-session](https://github.com/scitex-ai/scitex-session) | `scitex.session` | L3 | `@session` decorator + lifecycle management |
| [scitex-writer](https://github.com/scitex-ai/scitex-writer) | `scitex.writer` | L3 | LaTeX manuscript compilation, versioning, diffs |
| [scitex-genai](https://github.com/scitex-ai/scitex-genai) | `scitex.genai` | L3 | Generative-AI provider abstraction (LLM, agents, media) |
| [scitex-ml](https://github.com/scitex-ai/scitex-ml) | `scitex.ml` | L3 | Machine-learning classification and training utilities |
| [scitex-notebook](https://github.com/scitex-ai/scitex-notebook) | `scitex.notebook` | L3 | Jupyter notebook verification and DAG-based conversion |
| [scitex-todo](https://github.com/scitex-ai/scitex-todo) | `scitex.todo` | L3 | Canonical YAML task store with mermaid dependency graphs |
| [scitex-ui](https://github.com/scitex-ai/scitex-ui) | `scitex.ui` | L3 | Shared frontend UI components |
| [figrecipe](https://github.com/scitex-ai/figrecipe) | `scitex.fig`, `scitex.plt` | L2 | Reproducible matplotlib wrapper, mm-precision layouts |
| [scitex-stats](https://github.com/scitex-ai/scitex-stats) | `scitex.stats` | L2 | 23 statistical tests, effect sizes, power analysis |
| [scitex-dsp](https://github.com/scitex-ai/scitex-dsp) | `scitex.dsp` | L2 | Digital signal processing — PAC, Hilbert, wavelet, filters |
| [scitex-nn](https://github.com/scitex-ai/scitex-nn) | `scitex.nn` | L2 | Neural-network building blocks |
| [scitex-io](https://github.com/scitex-ai/scitex-io) | `scitex.io` | L1 | Universal scientific data I/O, 30+ format plugins |
| [crossref-local](https://github.com/scitex-ai/crossref-local) | `scitex.scholar.crossref` | L1 | Local CrossRef database, 167M+ works, full-text search |
| [openalex-local](https://github.com/scitex-ai/openalex-local) | `scitex.scholar.openalex` | L1 | Local OpenAlex database, 284M+ works, semantic search |
| [scitex-dev](https://github.com/scitex-ai/scitex-dev) | `scitex.dev` | L0 | Shared developer utilities and AST linter |
| [scitex-hub](https://github.com/scitex-ai/scitex-hub) | `scitex.cloud` | Orthogonal | Deployment and management CLI — live at [scitex.ai](https://scitex.ai) |
| [scitex-agent-container](https://github.com/scitex-ai/scitex-agent-container) | `scitex.agent_container` | Orthogonal | Declarative framework for AI coding-agent fleets |
| [scitex-orochi](https://github.com/scitex-ai/scitex-orochi) | `scitex.orochi` | Orthogonal | Agent communication hub |
| [scitex-container](https://github.com/scitex-ai/scitex-container) | `scitex.container` | Orthogonal | Unified Apptainer/Docker container management |

*The remaining L0–L2 tooling packages (`scitex-path`, `scitex-str`, `scitex-config`, and
similar small utility leaves) are listed in each package's own README and in the
[full registry](https://github.com/scitex-ai/scitex-dev/blob/main/src/scitex_dev/_ecosystem/_registry.py).*

</details>

---

## License

SciTeX packages are mainly licensed under AGPL-3.0 — check each repository's own
LICENSE file, as a small number of peripheral tools differ.

## Contact

info@scitex.ai

---

<p align="center">
  <a href="https://scitex.ai"><img src="assets/scitex-icon.png" alt="SciTeX" width="40"/></a>
</p>
