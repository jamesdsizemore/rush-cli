"""Polyglot AST outline compressor for TypeScript, JavaScript, Rust, and Go."""

from __future__ import annotations


class PolyglotAstCompressor:
    """Extracts type signatures and function prototypes across multiple languages."""

    @staticmethod
    def compress_typescript(ts_source: str) -> str:
        lines = []
        for line in ts_source.splitlines():
            line_clean = line.strip()
            if line_clean.startswith(
                (
                    "export function",
                    "function",
                    "export const",
                    "export interface",
                    "export type",
                    "export class",
                    "class",
                )
            ):
                if "{" in line:
                    sig = line.split("{")[0].strip()
                    lines.append(f"{sig} {{ ... }}")
                else:
                    lines.append(line)
        return "\n".join(lines)

    @staticmethod
    def compress_rust(rs_source: str) -> str:
        lines = []
        for line in rs_source.splitlines():
            line_clean = line.strip()
            if line_clean.startswith(
                (
                    "pub fn",
                    "fn",
                    "pub struct",
                    "struct",
                    "pub enum",
                    "enum",
                    "pub trait",
                    "trait",
                    "impl",
                )
            ):
                if "{" in line:
                    sig = line.split("{")[0].strip()
                    lines.append(f"{sig} {{ ... }}")
                else:
                    lines.append(line)
        return "\n".join(lines)

    @staticmethod
    def compress_go(go_source: str) -> str:
        lines = []
        for line in go_source.splitlines():
            line_clean = line.strip()
            if line_clean.startswith(("func ", "type ", "interface ")):
                if "{" in line:
                    sig = line.split("{")[0].strip()
                    lines.append(f"{sig} {{ ... }}")
                else:
                    lines.append(line)
        return "\n".join(lines)
