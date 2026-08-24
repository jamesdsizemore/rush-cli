# Rush local and optional remote model intelligence — research report

Research date: 2026-08-23. Scope: local-first model intelligence for Rush's memory, retrieval, context, privacy, and bounded agent workflows—not a chat UI, generic model runner, or provider proxy. All model/card/provider claims below link to a primary source. “Fits” means a planning hypothesis that must be measured with the stated runtime, context length, and quantization; parameter count or advertised maximum context is not proof of consumer-hardware fit.

## 1. Recommendation in one page

**Ship no model as a mandatory Rush dependency.** The C0 baseline must be useful with no model installed: SQLite FTS5, deterministic parsers, first-party span recognizers, and a discovered Gitleaks engine. Add a user-provisioned local embedding engine next; add optional local language-model transforms only after the corpus proves they preserve evidence and reduce context. Remote models are explicit, redacted, user-controlled augmentations—never a fallback for missing local hardware.

| System | Required? | Recommended choice | Why |
|---|---|---|---|
| C0 universal local baseline | Yes, but model-free | SQLite FTS5 + exact filters; deterministic secret/PII scan; Pydantic/JSON Schema; optional Gitleaks executable | Works offline on ordinary hardware and has no downloaded model, account, cloud, or daemon. |
| Local semantic baseline | Opportunistic | [IBM Granite Embedding 278M multilingual](https://huggingface.co/ibm-granite/granite-embedding-278m-multilingual) through ONNX Runtime/FastEmbed, with [BGE-small-en-v1.5](https://huggingface.co/BAAI/bge-small-en-v1.5) as an English control | Apache-2.0/MIT, CPU-capable, bounded artifact size; a model engine remains optional. |
| Enhanced retrieval | Opt-in C1/C2 | [Qwen3-Embedding-0.6B](https://huggingface.co/Qwen/Qwen3-Embedding-0.6B) + [Qwen3-Reranker-0.6B](https://huggingface.co/Qwen/Qwen3-Reranker-0.6B) | Apache-2.0, 32K/1,024D embedding and instruction-aware reranking; prove benefit on Rush corpus before shipping. |
| Local utility model | Opt-in | [Qwen3-4B](https://huggingface.co/Qwen/Qwen3-4B), [Phi-4-mini-instruct](https://huggingface.co/microsoft/Phi-4-mini-instruct), and [SmolLM3-3B](https://huggingface.co/HuggingFaceTB/SmolLM3-3B) comparison set | 3–4B models are plausible for bounded extract/classify/reduce/validate work on a 16-GB machine; none writes canonical memory. |
| General local model | Opt-in C1 | [Qwen3-8B](https://huggingface.co/Qwen/Qwen3-8B), [Granite-3.3-8B-Instruct](https://huggingface.co/ibm-granite/granite-3.3-8b-instruct), [Qwen2.5-Coder-7B-Instruct](https://huggingface.co/Qwen/Qwen2.5-Coder-7B-Instruct) | The first genuinely useful 8B class for code-bearing, schema-constrained transforms; require 12–16 GB VRAM or suitable unified memory for reliable 8–16K use. |
| Advanced local code model | Optional C2 only | [gpt-oss-20b](https://huggingface.co/openai/gpt-oss-20b), [Qwen3-Coder-30B-A3B](https://huggingface.co/Qwen/Qwen3-Coder-30B-A3B-Instruct), [Devstral Small 2 24B](https://huggingface.co/mistralai/Devstral-Small-2-24B-Instruct-2512) | Candidate comparators for 16–24 GB VRAM / 32–64 GB unified/RAM. They are not defaults and may be slower or less token-efficient than a deterministic projection. |
| Sensitive-data barrier | Yes | first-party span rules + [Gitleaks](https://github.com/gitleaks/gitleaks) when discovered; optional [Presidio](https://github.com/microsoft/presidio) then [GLiNER PII](https://huggingface.co/urchade/gliner_multi_pii-v1) | Deterministic local detection runs before persistence **and again** on the final remote request. An LLM is never the first privacy gate. |
| Remote augmentation | Optional | Direct OpenAI, Anthropic, Gemini, Z.AI, and DeepSeek APIs; OAuth-owned Codex, Claude Code, and Antigravity CLI bridges; 9Router/OmniRouter named verification tracks | User initiation plus documented provider capabilities. Local-only mode never silently egresses; Rush never imports CLI credentials. |

## 2. Evidence method and score key

Research used official Hugging Face model cards/artifacts, GitHub repositories/releases, primary runtime documentation, original benchmark/documentation sources, and official provider privacy/authentication documents. Model artifacts must be identified at execution by immutable Hugging Face revision plus file SHA-256, not model name alone. Vendor benchmarks are candidate-inclusion evidence only; Rush selection follows the private/synthetic benchmark in section 11.

Each serious candidate receives a compact 0–5 score string in this order: `A/O/H/Q/T/P/S/L/M/C/K/U/D/V/R` = Rush architecture fit, offline fit, consumer hardware fit, task quality, token-efficiency contribution, privacy/data control, security/redaction compatibility, license compatibility, maintenance, integration complexity (higher is easier), provider lock-in resistance, user value, differentiation, time-to-value, and decline risk (higher is safer). Scores are comparative research priors; the rationale/decision column states why.

## 3. Consumer hardware profiles

| Profile | Reliable local functions | Baseline / enhanced models | Keep deterministic or disabled | Fallback |
|---|---|---|---|---|
| C0: CPU-only, 8–16 GB RAM | FTS5, exact filtering, parsing, secret/PII rules, Gitleaks; small ONNX embedding only if provisioned | Granite 278M int8, BGE-small, MiniLM | Rerank, OCR, local LLM, ANN daemon, large document AI extraction | Structured `skipped`; lexical retrieval and deterministic projection remain fully usable. |
| C1a: 16 GB RAM laptop/desktop | C0 plus small embedding; modest 3–4B Q4 model at 4–8K only after measurement | Qwen3-4B / Phi-4-mini / SmolLM3; mxbai/BGE-M3 quantized where memory permits | 7B+ response-critical path, 16K+ context promises, concurrent engines | Use C0 path; user may choose remote only after egress approval. |
| C1b: 8 GB VRAM + 16 GB RAM | C1a plus local 3–4B Q4; light rerank top-k | Qwen3 embed/rerank 0.6B at bounded batches | 8B at large context, 14B+, concurrent LLM/reranker | Reduce top-k / disable rerank / return `skipped`. |
| C2: 12–16 GB VRAM + 32 GB RAM | 7–8B Q4 at 8–16K; enhanced embeddings/rerank; local optional OCR | Qwen3-8B, Granite 8B, Qwen2.5-Coder 7B; gpt-oss-20b only with exact 16-GB profile | 24B+ or 30B+ at claimed maximum context | Fall back to 3–4B transform or deterministic route. |
| Apple 16 GB unified | C1a via MLX or Metal/GGUF; no cloud required | 3–8B Q4 at 4–8K; Granite/BGE embedding | 20–30B day-to-day, parallel models | C0/embedding path. |
| Apple 24–32 GB unified | C2-like 7–14B local path, model-by-model | Qwen3-8B, code 7B; exact gpt-oss/24B test only | 256K from card maximum | C1 model with reduced context. |
| C3: 24 GB VRAM or 48–64 GB unified/RAM | Advanced 20–30B Q4 with 4–8K context; 4B embedding quality comparator | gpt-oss-20b, Devstral 24B, Qwen3-Coder 30B | “All models at 128–256K,” server assumptions | C2 general baseline. |
| Higher-memory workstation | Batch reindex / advanced comparators only | Qwen3-Embedding-4B, BGE-M3 hybrid, advanced code models | A required product path | Same capability registry; nothing special is trusted by virtue of size. |

The [llama.cpp quantization guidance](https://github.com/ggml-org/llama.cpp/blob/master/tools/quantize/README.md) makes the important constraint explicit: weights are loaded into memory and KV/runtime headroom is additional. Hardware support is therefore tested at 1K/4K/8K/16K contexts, not inferred from a card’s 128K/256K architectural maximum.

## 4. Embeddings, rerankers, and retrieval catalog

| Candidate (direct source) | Key facts, format, realistic tier | Score | Recommendation and rationale |
|---|---|---:|---|
| [Qwen3-Embedding-0.6B](https://huggingface.co/Qwen/Qwen3-Embedding-0.6B) | Apache-2.0; 0.6B; 32K; 1,024D MRL 32–1,024; 100+ languages | `5/5/4/5/5/5/4/5/5/4/5/5/5/4/4` | Enhanced default candidate. Strong technical fit, but BF16 is ~1.2 GB and long inputs need measured CPU/KV limits. |
| [Qwen3-Reranker-0.6B](https://huggingface.co/Qwen/Qwen3-Reranker-0.6B) | Apache-2.0; 0.6B; 32K instruction-aware cross-encoder | `5/5/4/5/5/5/4/5/5/4/5/5/4/4/4` | C1 top-10–30 reranker only; must lower final context without losing required evidence. |
| [Granite Embedding 278M multilingual](https://huggingface.co/ibm-granite/granite-embedding-278m-multilingual) | Apache-2.0; 278M; 768D; 512 tokens; 12 languages | `5/5/5/4/4/5/5/5/5/5/5/5/4/5/5` | Recommended CPU baseline. Chunk long material explicitly; 512-token limit excludes silent whole-file embedding. |
| [EmbeddingGemma 300M](https://huggingface.co/google/embeddinggemma-300m) | Gemma terms; 300M; 100+ languages; MRL 768/512/256/128 | `4/5/5/4/5/5/4/3/5/4/5/5/4/4/3` | Excellent device candidate, but license acceptance/review is a hard gate. |
| [Nomic Embed Text v1.5](https://huggingface.co/nomic-ai/nomic-embed-text-v1.5) | Apache-2.0; 0.1B; 768D MRL 64–768; 8,192 tokens; ONNX/GGUF | `4/5/5/4/5/5/3/5/4/3/5/5/4/5/3` | Long-context C0 comparator. Reject the card’s `trust_remote_code=True` route; use reviewed native/ONNX/GGUF only. |
| [BGE-small-en-v1.5](https://huggingface.co/BAAI/bge-small-en-v1.5) | MIT; 384D; 512 tokens; ~133 MB weights | `5/5/5/3/4/5/5/5/5/5/5/4/3/5/5` | English control and emergency baseline, not product semantic default. |
| [all-MiniLM-L6-v2](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2) | Apache-2.0; 384D; 256 word pieces | `5/5/5/2/3/5/5/5/5/5/5/3/2/5/5` | Tiny control only; not adequate for code files or long handoffs. |
| [mxbai-embed-large-v1](https://huggingface.co/mixedbread-ai/mxbai-embed-large-v1) | Apache-2.0; 0.3B; ONNX/OpenVINO/GGUF; MRL/int8/binary | `5/5/5/4/5/5/4/5/4/5/5/5/4/4/4` | Enhanced English alternative; exact required query prompt is part of model provenance. |
| [mxbai-rerank-large-v1](https://huggingface.co/mixedbread-ai/mxbai-rerank-large-v1) | Apache-2.0; 0.4B; ONNX | `5/5/4/4/4/5/4/5/4/5/5/4/3/4/4` | English rerank comparator. |
| [BGE-M3](https://huggingface.co/BAAI/bge-m3) | MIT; 1,024D; 8,192 tokens; dense+sparse+ColBERT; multilingual | `4/5/2/5/5/5/4/5/5/4/5/5/5/3/4` | C1/C2 hybrid comparator; do not enable three retrieval modes before each proves value. |
| [BGE-reranker-v2-m3](https://huggingface.co/BAAI/bge-reranker-v2-m3) | Apache-2.0; multilingual XLM-R cross-encoder | `4/5/3/4/4/5/4/5/5/4/5/5/4/3/4` | Enhanced multilingual rerank comparator. |
| [multilingual-e5-large-instruct](https://huggingface.co/intfloat/multilingual-e5-large-instruct) | MIT; 1,024D; 512 tokens; 100 languages; ONNX | `4/5/3/4/4/5/4/5/5/5/5/4/3/4/5` | Mature multilingual control; query prefix correctness is mandatory. |
| [Snowflake Arctic Embed L v2](https://huggingface.co/Snowflake/snowflake-arctic-embed-l-v2.0) | Apache-2.0; 0.6B; 74 languages; ONNX | `4/5/3/4/4/5/4/5/5/4/5/4/3/3/4` | C1/C2 comparator; full artifact footprint is not C0. |
| [Jina Embeddings v3](https://huggingface.co/jinaai/jina-embeddings-v3) | CC-BY-NC-4.0; 0.6B; 8,192; 94 languages | `4/5/3/5/5/5/3/0/4/3/4/4/4/3/0` | Quality reference only: public terms block product shipment. |
| [Jina Reranker v2 multilingual](https://huggingface.co/jinaai/jina-reranker-v2-base-multilingual) | CC-BY-NC-4.0; 278M; 1,024 chunks; 94 languages | `4/5/4/4/4/5/3/0/4/4/4/4/3/3/0` | Decline for product use on license. |
| [GTE-Qwen2-1.5B](https://huggingface.co/Alibaba-NLP/gte-Qwen2-1.5B-instruct) | Apache-2.0; 1.5B; 1,536D; 32K; card uses `trust_remote_code` | `4/5/2/5/5/5/2/5/4/2/5/4/4/2/2` | Advanced reference only; Windows/runtime risk and remote-code path preclude baseline. |
| [Qwen3-Embedding-4B](https://huggingface.co/Qwen/Qwen3-Embedding-4B) | Apache-2.0; 4B; 32K; 2,560D MRL | `4/5/1/5/5/5/4/5/5/3/5/4/4/1/3` | C2 quality comparator, never a requirement. |
| [BGE-large-en-v1.5](https://huggingface.co/BAAI/bge-large-en-v1.5) | MIT; 1,024D; 512 tokens; ONNX | `5/5/3/4/3/5/5/5/5/5/5/4/3/4/5` | Mature English quality control. |

Storage is separate from inference. **Require** [SQLite FTS5](https://www.sqlite.org/fts5.html) as lexical baseline. Compare optional [hnswlib](https://github.com/nmslib/hnswlib), [USearch](https://github.com/unum-cloud/usearch), and [sqlite-vec](https://github.com/asg017/sqlite-vec) while SQLite remains the sole evidence/provenance authority. Use [FAISS](https://github.com/facebookresearch/faiss) as an accuracy oracle only; defer [LanceDB](https://github.com/lancedb/lancedb), [Qdrant local mode](https://github.com/qdrant/qdrant-client), and [Chroma](https://github.com/chroma-core/chroma) because their storage/packaging surface is unnecessary before simple local indexes fail the corpus.

## 5. Local utility/coding models

| Model (source) | Exact model facts and consumer fit | Score | Rush task / disposition |
|---|---|---:|---|
| [Qwen3-4B](https://huggingface.co/Qwen/Qwen3-4B) | 2025-04-29; Apache-2.0; dense 4B; 32K; Q4 ~2.6–3.2 GB | `5/5/5/4/4/5/4/5/5/5/5/5/4/5/5` | Minimum local transform candidate: classify, extract, constrained summary. CPU 12–16 GB/8-GB GPU, 4–8K test. |
| [Qwen3-8B](https://huggingface.co/Qwen/Qwen3-8B) | 2025-04-29; Apache-2.0; dense 8B; 128K architectural max; Q4 ~5–6 GB | `5/5/4/5/5/5/4/5/5/4/5/5/5/4/4` | General local baseline candidate; test only 8K/16K on C2. |
| [Qwen2.5-Coder-7B-Instruct](https://huggingface.co/Qwen/Qwen2.5-Coder-7B-Instruct) | Apache-2.0; 7.61B; 131K max; official GGUF | `5/5/4/4/4/5/4/5/5/5/5/5/4/4/5` | Code-bearing continuation comparator; do not assume coding scores equal memory reduction. |
| [Phi-4-mini-instruct](https://huggingface.co/microsoft/Phi-4-mini-instruct) | 2025-02-26; MIT; 3.8B; 128K; ONNX; explicit JSON/tool template | `5/5/5/4/4/5/4/5/4/5/5/5/4/5/5` | Strong small structured-output candidate. Pin chat template; test 8K. |
| [SmolLM3-3B](https://huggingface.co/HuggingFaceTB/SmolLM3-3B) | 2025-07-08; Apache-2.0; 3B; 64K trained/128K YaRN; tool calling | `5/5/5/4/4/5/4/5/5/5/5/5/4/5/5` | Fully open tiny candidate; known long-context degradation requires hard 8K/16K checks. |
| [Gemma 3 4B IT](https://huggingface.co/google/gemma-3-4b-it) | 2025-03-12; Gemma terms; text+image; 128K input/8K output | `4/5/4/4/4/5/3/2/5/4/4/4/4/3/2` | Vision control candidate only; gated terms and vision memory lower baseline value. |
| [Llama 3.2 3B Instruct](https://huggingface.co/meta-llama/Llama-3.2-3B-Instruct) | Llama Community License; 3B; 128K; mature GGUF/Ollama/MLX | `4/5/5/3/3/5/3/2/5/5/4/3/2/4/2` | Compatibility control only, not default. |
| [Granite-3.3-8B-Instruct](https://huggingface.co/ibm-granite/granite-3.3-8b-instruct) | 2025-04-16; Apache-2.0; 8B; 128K; FIM/thinking delimiters | `5/5/4/5/4/5/4/5/4/4/5/5/4/4/4` | C2 governed-transform candidate; never persist thinking delimiters. |
| [DeepSeek-R1-Distill-Qwen-7B](https://huggingface.co/deepseek-ai/DeepSeek-R1-Distill-Qwen-7B) | 2025-01-20; MIT; 7B reasoning distill | `4/5/4/4/2/5/3/5/5/4/5/4/3/3/4` | Reasoning comparator only; verbose reasoning can raise tokens/latency. |
| [gpt-oss-20b](https://huggingface.co/openai/gpt-oss-20b) | 2025-08-05; Apache-2.0; 21B total/3.6B active MoE; native MXFP4; official 16-GB minimum | `4/5/3/5/4/5/4/5/5/3/5/5/5/3/4` | Enhanced C2 model/tool-use comparator; Harmony format and no-CoT persistence are mandatory. |
| [Qwen3-Coder-30B-A3B](https://huggingface.co/Qwen/Qwen3-Coder-30B-A3B-Instruct) | 2025-07-22; Apache-2.0; MoE 30.5B/3.3B active; 256K max | `3/5/1/5/4/5/4/5/5/3/5/4/5/2/3` | 24-GB VRAM / 48–64-GB memory advanced code comparator. All weights still reside locally. |
| [Devstral Small 2 24B](https://huggingface.co/mistralai/Devstral-Small-2-24B-Instruct-2512) | 2025-12; Apache-2.0; dense 24B vision; 256K max | `3/5/2/5/4/5/4/5/4/3/5/4/5/2/3` | C3 coding benchmark candidate. Model-card SWE claims do not substitute for Rush corpus. |
| [Ministral 3 8B](https://huggingface.co/mistralai/Ministral-3-8B-Instruct-2512) | 2025-12; Apache-2.0; vision/instruct; 256K; official FP8 repo ~20.9 GB | `3/5/3/4/4/5/4/5/4/3/5/4/4/3/3` | Format/runtime compatibility research only; no trusted consumer quantization assumption. |
| [Mistral Small 3.1 24B](https://huggingface.co/mistralai/Mistral-Small-3.1-24B-Instruct-2503) | 2025-03; Apache-2.0; 24B vision/tool/JSON; 128K | `3/5/2/5/4/5/4/5/4/3/5/4/4/2/3` | C3 vision/general alternative, only if corpus beat justifies it. |

Bounded model tasks: taxonomy classification, metadata extraction with span IDs, structured candidate proposals, relevance routing, confidence labels, or **derived** summary alternatives. Model outputs are rejected if schema-invalid, untraceable, contain a secret, conflict with current authority, exceed budget, or cannot be reproduced as a model-proposed delta. They never auto-promote facts, rules, or guardrails.

## 6. Privacy, secret detection, parsing, and constrained extraction

| Candidate | License / consumer fit | Score | Decision |
|---|---|---:|---|
| [Gitleaks](https://github.com/gitleaks/gitleaks) | MIT; local binary; maintained releases | `5/5/5/4/4/5/5/5/5/5/5/5/4/5/5` | Preferred discovered secret engine; no hook installation. |
| [detect-secrets](https://github.com/Yelp/detect-secrets) | Apache-2.0 Python; local baseline/plugins | `5/5/5/4/3/5/5/5/4/5/5/4/3/5/4` | Secondary comparator. |
| [TruffleHog](https://github.com/trufflesecurity/trufflehog) | AGPL-3.0; verified secrets | `2/5/5/5/3/5/3/0/5/2/5/4/3/2/0` | Decline: license and unstable public library API. |
| [git-secrets](https://github.com/awslabs/git-secrets) | Apache-2.0 but hook-centric | `3/5/5/2/2/5/4/5/3/4/5/3/2/3/3` | Decline: wrong commit-hook workflow. |
| [Microsoft Presidio](https://github.com/microsoft/presidio) | MIT; Python; optional spaCy/transformers | `5/5/4/4/3/5/5/5/5/4/5/5/4/4/4` | Optional contextual PII adapter after deterministic spans. |
| [spaCy](https://github.com/explosion/spaCy) | MIT; compact CPU NER models | `5/5/5/3/2/5/4/5/5/5/5/4/3/5/5` | Presidio C0/C1 optional engine, not PII policy itself. |
| [GLiNER multi PII](https://huggingface.co/urchade/gliner_multi_pii-v1) | Apache-2.0 stated; local model | `4/5/3/4/3/5/4/5/4/4/5/4/4/3/3` | C1/C2 recall experiment only with pinned revision/safetensors. |
| [Piiranha v1](https://huggingface.co/iiiorg/piiranha-v1-detect-personal-information) | 280M PII model; public card needs artifact/legal verification | `3/5/3/4/3/5/3/3/2/3/5/3/3/2/2` | Comparator only. |
| [Stanza](https://github.com/stanfordnlp/stanza) | Apache-2.0 library; downloaded data has separate review needs | `3/5/3/4/2/5/3/3/4/3/5/3/3/2/2` | Decline v1; model archive ingestion risk. |
| [scrubadub](https://github.com/LeapBeyond/scrubadub) | Apache-2.0 local patterns | `4/5/5/2/2/5/4/5/3/5/5/3/2/5/4` | Borrow pattern ideas only. |

Deterministic parse/validation first: [Pydantic](https://github.com/pydantic/pydantic) (MIT), [python-jsonschema](https://github.com/python-jsonschema/jsonschema) (MIT), [pypdf](https://github.com/py-pdf/pypdf) (BSD-3), [pdfplumber](https://github.com/jsvine/pdfplumber) (MIT), [Tesseract](https://github.com/tesseract-ocr/tesseract) (Apache-2.0), [OCRmyPDF](https://github.com/ocrmypdf/OCRmyPDF) (MPL-2.0). Advanced/declined comparisons: [Docling](https://github.com/docling-project/docling) (MIT, optional C2 engine), [Unstructured](https://github.com/Unstructured-IO/unstructured) (Apache-2.0 but dependency breadth), [Apache Tika](https://github.com/apache/tika) (Apache-2.0 but Java/parser surface), [LM Format Enforcer](https://github.com/noamgat/lm-format-enforcer) (MIT), [Outlines](https://github.com/outlines-dev/outlines) (Apache-2.0), [Guidance](https://github.com/guidance-ai/guidance) (MIT), [Jsonformer](https://github.com/1rgs/jsonformer) (MIT, decline stale/narrow), and [BAML](https://github.com/BoundaryML/baml) (Apache-2.0, decline DSL/provider layer).

Pipeline, with bounded byte/page/decompression/time limits and source-offset maps:

```text
untrusted bytes → deterministic parser → deterministic secret/PII spans
→ optional local PII/NER recall → policy decision → redacted durable projection
→ final rendered remote request → independent secret/PII scan → allowed remote call
```

Never retain a secret value. Findings store detector, source range, severity, and keyed redacted fingerprint only. Any ambiguous high-risk finding denies remote egress. Pydantic-valid output is not truth: a model-derived field needs source span, confidence, transform provenance, and verification status.

## 7. Local runtimes and packaging

| Runtime / architecture | License and exact source | Fit and decision |
|---|---|---|
| [ONNX Runtime](https://github.com/microsoft/onnxruntime) | MIT; [official quantization documentation](https://onnxruntime.ai/docs/performance/model-optimizations/quantization.html) | Evaluate first for CPU Windows/Linux embedding/NER. Quantization quality must be measured. |
| [FastEmbed](https://github.com/qdrant/fastembed) | Apache-2.0; ONNX Runtime default | Preferred Python adapter candidate; explicit artifact directory and offline mode required. |
| [sentence-transformers](https://github.com/UKPLab/sentence-transformers) | Apache-2.0 | Broad reference harness; PyTorch breadth excludes default dependency. |
| [llama.cpp](https://github.com/ggml-org/llama.cpp) | MIT; GGUF, local CPU/GPU, Windows, local OpenAI-compatible server | Cross-platform LLM benchmark adapter, not required runtime. Trust conversion provenance; bind loopback only. |
| [Ollama](https://github.com/ollama/ollama) | MIT; [local/cloud distinction](https://docs.ollama.com/faq) | Easy user runtime adapter after local-only settings/egress proof. Do not rely on cloud default behavior. |
| [LM Studio](https://lmstudio.ai/docs/app/offline) | Proprietary desktop app; offline local server documentation | User-managed desktop runtime adapter; no Rush dependency. |
| [MLX / mlx-lm](https://github.com/ml-explore/mlx-lm) | MIT; Apple Silicon | Apple-only local adapter; never cross-platform default. |
| [OpenVINO](https://github.com/openvinotoolkit/openvino) | Apache-2.0 | Intel CPU/iGPU conditional adapter, not universal baseline. |
| [vLLM](https://github.com/vllm-project/vllm) | Apache-2.0 | Server/workstation benchmark only; too heavy for consumer baseline. |
| [Transformers](https://github.com/huggingface/transformers) | Apache-2.0 | Reference/integration harness only; no unreviewed `trust_remote_code`. |

## 8. Remote providers, OAuth, existing CLIs, and routers

**Decision:** provider-supported OAuth and a user-authorized existing-CLI bridge are first-class integration routes, alongside direct API keys. Rush must never scrape, copy, import, or forward a CLI's OAuth/session token. Instead, it invokes a user-installed CLI under a narrowly declared, noninteractive profile and receives only structured output/provenance. The user completes sign-in in the provider's own browser/CLI flow; Rush can probe whether that CLI is installed and authenticated without inspecting its credential store.

| Provider / route | Official evidence | Rush disposition |
|---|---|---|
| [OpenAI Responses API](https://platform.openai.com/docs/quickstart/make-your-first-api-request) | API keys; [data controls](https://platform.openai.com/docs/models/default-usage-policies-by-endpoint) describe default abuse-monitoring retention and ZDR/MAM eligibility | Direct optional API-key adapter with store=false where supported, policy disclosure, and no ZDR assumption. |
| **OpenAI Codex CLI OAuth / CLI bridge** — [sign in with ChatGPT](https://help.openai.com/en/articles/11381614-api-codex-cli-and-sign-in-with-chatgpt), [Codex CLI](https://github.com/openai/codex) | codex --login has a provider-owned ChatGPT sign-in flow that stores credentials locally; Codex supports noninteractive structured execution | **In scope.** User signs in to Codex; Rush's codex bridge uses an installed, version-pinned executable, a read-only/explicitly approved execution profile, bounded input, and JSONL output. It never reads CODEX_HOME, browser state, or OAuth/API material. |
| [Anthropic Messages API](https://platform.claude.com/docs/en/manage-claude/authentication) | Direct API auth; retention/ZDR is arrangement/model-feature dependent | Direct optional API-key/WIF route after current-policy disclosure. |
| **Claude Code OAuth / CLI bridge** — [Claude Code authentication](https://docs.anthropic.com/en/docs/claude-code/getting-started), [CLI reference](https://docs.anthropic.com/en/docs/claude-code/cli-usage) | Claude Code supports Console OAuth and Claude App (Pro/Max) sign-in; claude -p supports JSON/stream-JSON output, session IDs, and bounded turns | **In scope.** User completes Claude's own login; Rush delegates only a constrained, no-secret, no-write capability and records CLI/version/model/session/provenance—not credentials or raw trajectory. |
| **Google Antigravity CLI OAuth / CLI bridge** — [installation & auth](https://antigravity.google/docs/cli/install/), [headless mode](https://antigravity.google/docs/cli/headless/) | agy uses OS-keyring profiles and browser/SSH OAuth; agy -p offers headless stdout with diagnostics on stderr; Gemini API-key/ADC modes are also documented | **In scope.** User authorizes Google sign-in/ADC/key in Antigravity itself; Rush invokes a declared agy profile with scoped permissions and parses only documented output. No keyring read, token export, or implicit Google account action. |
| [Gemini API](https://ai.google.dev/gemini-api/docs/get-started) | API/auth keys; [official OAuth](https://ai.google.dev/gemini-api/docs/oauth) requires a Cloud project and user-initiated flow | Direct optional adapter; OAuth only by provider-documented flow. Antigravity remains a separate CLI-provider path. |
| **Z.AI / GLM** — [API auth](https://docs.z.ai/api-reference/introduction), [Claude Code integration](https://docs.z.ai/devpack/tool/claude), [OpenCode integration](https://docs.z.ai/devpack/tool/opencode) | Current official documentation specifies Bearer API keys and supported coding-tool configuration, not a Rush-owned OAuth flow | **In scope.** Direct API-key adapter plus user-owned Claude Code/OpenCode bridge profiles. The GLM Coding Plan must be used only under its supported-tool terms; Rush does not extract Z.AI keys from another CLI. |
| **DeepSeek** — [API auth](https://api-docs.deepseek.com/api/deepseek-api), [official coding-agent integrations](https://api-docs.deepseek.com/guides/coding_agents/) | Current official documentation specifies Bearer API keys and OpenAI/Anthropic-compatible endpoints; it documents Claude Code/OpenCode integration, not a Rush-owned OAuth flow | **In scope.** Direct API-key adapter plus user-owned Claude Code/OpenCode bridge profiles. DeepSeek keys stay in the provider/CLI configuration or an OS secret reference, never Rush memory or logs. |
| [Mistral API](https://docs.mistral.ai/getting-started/quickstart/) | Official API-key/SDK path | Optional direct adapter after current terms/retention inspection. |
| [OpenRouter](https://openrouter.ai/docs/quickstart) | Compatible third-party API; separate privacy/retention policy | In-scope router track, with explicit provider allowlist, final redaction barrier, and policy receipt. |
| **9Router** — [9router.space](https://9router.space/9router-ai/) | Public evidence is presently insufficient to establish one authoritative identity/repository, auth method, retention policy, credential handling, and provider authority | **Remain in scope; do not reject.** Create a dedicated verification/integration track: identify the exact product and legal entity, obtain official API/OAuth/CLI contract and terms, validate endpoint/TLS/credential storage/retention/model routing, then ship a named adapter or CLI bridge if those gates pass. |
| **OmniRouter** — [hosted API docs](https://omnirouter.ru/docs/api-reference/) and separately named [OmniDimen/OmniRouter](https://github.com/OmniDimen/OmniRouter) | The same name identifies more than one product; hosted docs and the local GitHub project must not be conflated | **Remain in scope; do not reject.** First resolve the user's intended OmniRouter product/vendor and its official auth/OAuth/CLI, terms, retention, security, and compatibility contract. Then implement the specific approved route rather than silently downgrading it to a generic endpoint. |

CLI-bridge requirements: subprocess path is explicit and user-controlled; Rush passes only the redacted bounded request over stdin/arguments, uses the documented noninteractive JSON/JSONL mode, starts with no write/shell/network permissions beyond the provider CLI's established profile, has timeout/cancellation/output-size limits, and stores only a redacted result/provenance receipt. A bridge never opens a browser, logs in, changes a provider CLI's settings, reads its home/config/keychain files, carries its session across users, or assumes a CLI's subscription grants direct API rights.

Direct adapter requirements: credentials never reach a coding agent, logs, ToolResult, memory, bundle, or telemetry; configured provider IDs/model revisions/policy are inspectable; requests have timeouts/cancellation and no automatic cross-provider retry; response is a non-authoritative candidate with provider/model/request policy provenance; unavailable credentials/provider returns structured skipped.

## 9. Rush architecture and user workflows

Current verified touchpoints: `src/rush/tools/base.py::ToolResult`/`Finding`; `src/rush/tools/__init__.py` tool registry; `src/rush/cli.py::_run_tool`; `src/rush/mcp.py::_register_tools`; `src/rush/config.py::RushConfig` and parser; `src/rush/providers/base.py::LLMProvider.summarize_findings`; `src/rush/token_economy/router.py::ContentRouter`, `ccr_store.py::CCRStore`, `cache_aligner.py`, `stale_sweeper.py`, `telemetry.py::TelemetryStore`; `src/rush/codegraph/context_packer.py::ContextPacker`; `src/rush/session_memory.py::SessionMemoryManager`; `src/rush/safety/redactor.py::SecretRedactor`; `src/rush/safety/workspace_boundary.py::WorkspaceBoundaryGuard`; and `src/rush/permissions.py`.

Proposed Rush-owned contract:

```python
class IntelligenceCapability(Protocol):
    capability: Literal['embed', 'rerank', 'classify', 'extract', 'generate', 'pii_recall']
    async def probe(self) -> CapabilityStatus: ...
    async def invoke(self, request: IntelligenceRequest) -> IntelligenceResult: ...
```

`IntelligenceResult` carries provider/runtime/model ID, immutable revision/hash, license, locality, hardware/profile, input/output token or compute accounting, source IDs, schema-validation result, confidence, redaction decision, and a bounded error. It is not a `Claim`. Every engine is capability-discovered; unavailable local artifact/runtime/hardware or remote credential yields `ToolResult(status="skipped")` with a safe reason.

Vibecoder workflow: `rush intelligence recommend` reports one C0/C1 recommendation, disk/RAM/privacy implications, and a one-command user-provisioning instruction; `rush intelligence status` states local/remote/offline mode and why a capability is skipped. `rush intelligence provider connect <name> --mode cli` only probes a user-installed/sign-in-complete CLI and records an explicit approved bridge profile; `--mode oauth` launches only a provider-documented OAuth flow when the provider permits it. Experienced workflow: declare per-capability runtime/model, pinned revision, policy (`local_only`, `redact_before_remote`, `confirm_before_remote`, `no_retention`), hardware ceiling, allowed endpoints, and an allowed CLI binary/profile; inspect provenance/usage and disable any capability. Agent workflow: agents call explicit Rush tools such as `continuity_retrieve` or `intelligence_extract`; they receive structured candidates/provenance and never provider secrets.

## 10. Model-selection decision record

1. **C0 is model-free and required.** FTS5/exact retrieval, deterministic parsing, secret/PII spans, and redaction are the core guarantee.
2. **First local artifact gate:** Granite 278M + ONNX Runtime/FastEmbed; BGE-small is control. EmbeddingGemma remains legal-review-only.
3. **Enhanced gate:** Qwen3 0.6B embedding/reranker versus Nomic/mxbai/BGE-M3; HNSW/USearch/sqlite-vec are indexes only.
4. **Local LLM gate:** Qwen3-4B, Phi-4-mini, SmolLM3; Qwen3-8B/Granite 8B/code 7B only for C2; no LLM ships without a deterministic fallback.
5. **Remote and CLI-provider gate:** direct API, provider-owned OAuth, and user-authorized CLI bridges are peer routes. Codex, Claude Code, Antigravity, Z.AI, DeepSeek, 9Router, and OmniRouter remain in scope; each named route advances only after its specific auth, terms, retention, security, capability, and redaction-conformance record passes. No token copying, automatic provider switch, or generic-endpoint substitution.
6. **Absolute rule:** model output and vector ranking are evidence candidates. Repository/tool receipt/authority reducer stay canonical.

## 11. Benchmark and unresolved decisions

Build a private/synthetic 100+ case corpus: symbol/file search, continuation state, stale repository facts, contradictions, incomplete obligations, multilingual inputs, prompt-injection text, and secret-bearing blobs. Record Recall@k/nDCG@10/evidence-span precision, stale false positives, p50/p95 embedding/retrieval/rerank latency, peak RSS/VRAM, disk, index build/rebuild time, real token counts, completion/recovery accuracy, schema validity, secret leakage, and offline outbound connections.

Selection gates: all artifacts require pinned revision/file hash/license; no `trust_remote_code`; local means local weights/runtime, loopback binding, and verified no egress. **Token reduction is a primary product gate, not a side effect:** require at least 50% median continuation-input reduction with zero labeled critical-fact loss and no P95 increase; otherwise keep deterministic projection. Remote gate: final rendered input rescanned/redacted and confirmation/policy checked. Unresolved decisions: artifact provisioning UX; artifact cache location; OS credential-store coverage; exact latency budgets by profile; encryption-at-rest; whether the user wants a separately licensed Gemma option; and whether any provider’s OAuth terms permit Rush’s exact flow.

## 12. What not to build

- No general chat UI, hosted memory platform, model marketplace, daemon, auto-download, auto-hook, or agent-owned credential store.
- No remote fallback when local capability is unavailable.
- No automatic model/model-router selection that can egress data or change provider without approval.
- No opaque LLM summary as canonical memory, rule, evidence, or deletion decision.
- No vector database as the source of truth, no copied router OAuth/account pooling, and no claim that a model’s maximum context is supported consumer capacity.
