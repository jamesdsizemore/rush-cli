# Frequently asked questions

## Does Rush replace Ruff, ESLint, or pytest?

No. Rush selects and normalizes supported tools already installed in your environment.

## Does Rush install missing tools?

No. A missing optional helper produces `skipped`; you choose whether and how to install it.

## Does `ok` mean my code is correct?

No. It means the requested check completed without a blocking result. Quality still depends on scope, configuration, test coverage, and human judgment.

## Is `skipped` a failure?

Not automatically, but it is not proof of success. Teams should decide which checks must run and inspect JSON in CI.

## Does Rush use AI to review code?

Not currently. Default review is deterministic. Graft context is local and opt-in. `--llm` is a stub that makes no provider call.

## Does MCP expose Rush on my network?

No. Rush supports local stdio MCP only.

## Can Rush rewrite my files?

`review` and focused checks do not. `format` supports a check-only flag and has a non-check path that can invoke formatters; inspect and version-control your work before using any mutating formatter mode. Baseline and publication operations are guarded or unavailable.

## Why are advanced commands listed if they skip?

The catalog includes guarded and experimental capabilities to keep contracts visible while preventing unsafe execution. Documentation labels their actual maturity.

## Where do I report a security issue?

Follow [Security reporting](../maintainers/incident-and-security.md); do not post sensitive details publicly.

## Context Intelligence & Ship Readiness

* **`rush ship gate`**: Evaluates 7 release vectors in parallel.
* **`rush hallu-guard`**: Detects hallucinated or uninstalled package imports.
* **`rush token outline`**: Compresses file source code into AST outlines.
* **`rush context retrieve`**: Restores full uncompressed content from CCR cache.
