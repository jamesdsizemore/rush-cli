# Master Research Repository Inventory & Pinned Commit Manifest

## 1. Overview & Clean-Room Governance

To ensure maximum engineering rigor, reproducibility, and intellectual property protection, Rush maintains an exhaustive local research cache in `research/repos/` (which is untracked in `.gitignore` per [AGENTS.md](file:///C:/Users/james/developer/rush-cli/AGENTS.md)).

All **50 reference repositories, libraries, tools, and format specifications** analyzed across the innovation reports have been cloned locally, audited for licensing, and pinned to exact Git commit SHAs in `research/pinned-repos.json`.

Every capability in Rush is clean-room implemented in pure Python 3.12 under permissive MIT/Apache-2.0 licenses as mandated by [ADR-0044](file:///C:/Users/james/developer/rush-cli/docs/adr/0044-clean-room-implementation-of-codebase-indexing-algorithms.md).

---

## 2. Complete Pinned Repository Matrix (50 Repositories)

| Repository Name | Pinned Commit SHA | Upstream URL | Role / Innovation Pattern Extracted |
|---|:---:|---|---|
| `PixelPrune` | `8d347eb1bd` | [OPPO-Mente-Lab/PixelPrune](https://github.com/OPPO-Mente-Lab/PixelPrune) | Reference implementation, benchmark fixtures, and test suite. |
| `SMELT` | `7d6663a3c1` | [TooCas/SMELT](https://github.com/TooCas/SMELT) | Reference implementation, benchmark fixtures, and test suite. |
| `TokenTamer` | `cb2f06e7e7` | [borhen68/TokenTamer](https://github.com/borhen68/TokenTamer) | Reference implementation, benchmark fixtures, and test suite. |
| `TrueMemory` | `e7f1fd79e4` | [buildingjoshbetter/TrueMemory](https://github.com/buildingjoshbetter/TrueMemory) | Reference implementation, benchmark fixtures, and test suite. |
| `Wax` | `2fb341844a` | [christopherkarani/Wax](https://github.com/christopherkarani/Wax) | Reference implementation, benchmark fixtures, and test suite. |
| `ai-memory` | `b9b687b8d6` | [akitaonrails/ai-memory](https://github.com/akitaonrails/ai-memory) | Reference implementation, benchmark fixtures, and test suite. |
| `caveman` | `2f49f0e1a3` | [JuliusBrussee/caveman](https://github.com/JuliusBrussee/caveman) | Reference implementation, benchmark fixtures, and test suite. |
| `cc-session-reader` | `2c10e384d5` | [Mapleeeeeeeeeee/cc-session-reader](https://github.com/Mapleeeeeeeeeee/cc-session-reader) | Reference implementation, benchmark fixtures, and test suite. |
| `code2prompt` | `1af498e790` | [raphaelmansuy/code2prompt](https://github.com/raphaelmansuy/code2prompt.git) | Reference implementation, benchmark fixtures, and test suite. |
| `codegraph-cli` | `a4493dfda9` | [codegraph-cli](https://github.com/al1-nasir/codegraph-cli.git) | Reference implementation, benchmark fixtures, and test suite. |
| `codex-agent-mem` | `d594c8a862` | [MarceloCaporale/codex-agent-mem](https://github.com/MarceloCaporale/codex-agent-mem) | Reference implementation, benchmark fixtures, and test suite. |
| `engram` | `9fa2a4b74c` | [NickCirv/engram](https://github.com/NickCirv/engram) | Reference implementation, benchmark fixtures, and test suite. |
| `graft` | `65a76e5edd` | [NanoNets/context-graph-engine](https://github.com/NanoNets/context-graph-engine) | Reference implementation, benchmark fixtures, and test suite. |
| `grype` | `ab6707d1d5` | [anchore/grype](https://github.com/anchore/grype.git) | Reference implementation, benchmark fixtures, and test suite. |
| `headroom` | `91186b40d8` | [headroomlabs-ai/headroom](https://github.com/headroomlabs-ai/headroom) | Reference implementation, benchmark fixtures, and test suite. |
| `in-toto` | `a8ce9ee212` | [in-toto](https://github.com/in-toto/in-toto.git) | Reference implementation, benchmark fixtures, and test suite. |
| `in-toto-attestation` | `051624ce46` | [in-toto-attestation](https://github.com/in-toto/attestation.git) | Reference implementation, benchmark fixtures, and test suite. |
| `jusTokenMax` | `f4a06ee1cf` | [Kalmantic/jusTokenMax](https://github.com/Kalmantic/jusTokenMax) | Reference implementation, benchmark fixtures, and test suite. |
| `mcp-code-execution-enhanced` | `29bf586f07` | [yoloshii/mcp-code-execution-enhanced](https://github.com/yoloshii/mcp-code-execution-enhanced) | Reference implementation, benchmark fixtures, and test suite. |
| `mcp-codebase-index` | `ea8ad0b245` | [MikeRecognex/mcp-codebase-index](https://github.com/MikeRecognex/mcp-codebase-index) | Reference implementation, benchmark fixtures, and test suite. |
| `memmy-agent` | `ec10c754b0` | [MemTensor/memmy-agent](https://github.com/MemTensor/memmy-agent.git) | Reference implementation, benchmark fixtures, and test suite. |
| `octave-mcp` | `9876352e51` | [elevanaltd/octave-mcp](https://github.com/elevanaltd/octave-mcp) | Reference implementation, benchmark fixtures, and test suite. |
| `pg-schema-diff` | `9ada4710c2` | [stripe/pg-schema-diff](https://github.com/stripe/pg-schema-diff.git) | Reference implementation, benchmark fixtures, and test suite. |
| `pytest` | `df87db7b04` | [pytest-dev/pytest](https://github.com/pytest-dev/pytest.git) | Reference implementation, benchmark fixtures, and test suite. |
| `reducethemtokens` | `8694c60fa3` | [yttrium400/reducethemtokens](https://github.com/yttrium400/reducethemtokens) | Reference implementation, benchmark fixtures, and test suite. |
| `repomix` | `72807df37a` | [yamadashy/repomix](https://github.com/yamadashy/repomix.git) | Reference implementation, benchmark fixtures, and test suite. |
| `roam-code` | `bcea1a210a` | [Cranot/roam-code](https://github.com/Cranot/roam-code) | Reference implementation, benchmark fixtures, and test suite. |
| `rtk` | `29f9bb7161` | [rtk-ai/rtk](https://github.com/rtk-ai/rtk) | Reference implementation, benchmark fixtures, and test suite. |
| `ruff` | `fca5c7cf2c` | [astral-sh/ruff](https://github.com/astral-sh/ruff.git) | Reference implementation, benchmark fixtures, and test suite. |
| `semantica` | `1ee2ae88a7` | [semantica-agi/semantica](https://github.com/semantica-agi/semantica) | Reference implementation, benchmark fixtures, and test suite. |
| `setup-python` | `751276eafc` | [actions/setup-python](https://github.com/actions/setup-python) | Reference implementation, benchmark fixtures, and test suite. |
| `shiplog` | `04f1ed76ee` | [danielgwilson/shiplog](https://github.com/danielgwilson/shiplog.git) | Reference implementation, benchmark fixtures, and test suite. |
| `shipnote` | `1054c12762` | [Sev7nOfNine/shipnote](https://github.com/Sev7nOfNine/shipnote) | Reference implementation, benchmark fixtures, and test suite. |
| `sigmap` | `bd771432b2` | [manojmallick/sigmap](https://github.com/manojmallick/sigmap) | Reference implementation, benchmark fixtures, and test suite. |
| `sqlglot` | `ceb5111421` | [sqlglot](https://github.com/tobymao/sqlglot.git) | Reference implementation, benchmark fixtures, and test suite. |
| `stryker-js` | `de5ae70f3c` | [stryker-mutator/stryker-js](https://github.com/stryker-mutator/stryker-js.git) | Reference implementation, benchmark fixtures, and test suite. |
| `syft` | `bf82010f3c` | [anchore/syft](https://github.com/anchore/syft.git) | Reference implementation, benchmark fixtures, and test suite. |
| `tach` | `c599d3ab87` | [tach-org/tach](https://github.com/tach-org/tach.git) | Reference implementation, benchmark fixtures, and test suite. |
| `th0th` | `7936342948` | [S1LV4/th0th](https://github.com/S1LV4/th0th) | Reference implementation, benchmark fixtures, and test suite. |
| `tiktoken` | `4e71bbe0c0` | [tiktoken](https://github.com/openai/tiktoken.git) | Reference implementation, benchmark fixtures, and test suite. |
| `tokless` | `81d6f52fbb` | [HoangP8/tokless](https://github.com/HoangP8/tokless) | Reference implementation, benchmark fixtures, and test suite. |
| `toon` | `f06ddca16c` | [toon-format/toon](https://github.com/toon-format/toon) | Reference implementation, benchmark fixtures, and test suite. |
| `tooner` | `17b22aa165` | [chaindead/tooner](https://github.com/chaindead/tooner) | Reference implementation, benchmark fixtures, and test suite. |
| `tree-sitter` | `74b7d0c951` | [tree-sitter](https://github.com/tree-sitter/tree-sitter.git) | Reference implementation, benchmark fixtures, and test suite. |
| `tree-sitter-python` | `26855eabcc` | [tree-sitter-python](https://github.com/tree-sitter/tree-sitter-python.git) | Reference implementation, benchmark fixtures, and test suite. |
| `trufflehog` | `3ab759fef4` | [trufflesecurity/trufflehog](https://github.com/trufflesecurity/trufflehog.git) | Reference implementation, benchmark fixtures, and test suite. |
| `uteke` | `38a5db8eec` | [codecoradev/uteke](https://github.com/codecoradev/uteke) | Reference implementation, benchmark fixtures, and test suite. |
| `uv` | `26a9dd4b21` | [astral-sh/uv](https://github.com/astral-sh/uv.git) | Reference implementation, benchmark fixtures, and test suite. |
| `zep` | `7de18dfa14` | [getzep/zep](https://github.com/getzep/zep) | Reference implementation, benchmark fixtures, and test suite. |
| `zizmor` | `11bbf7e6cf` | [zizmorcore/zizmor](https://github.com/zizmorcore/zizmor.git) | Reference implementation, benchmark fixtures, and test suite. |

---

## 3. Local Offline Research Storage & Verification

* **Local Clone Directory**: `research/repos/`
* **Pinned Commit Ledger**: `research/pinned-repos.json`
* **Offline Verification**: All repositories are stored locally on-disk, allowing developers, test harnesses, and quality engines to inspect reference implementations, test fixtures, and grammar specifications 100% offline without network dependency.
