"""ContentRouter for classifying payload structures and routing to specialized distillers."""

from enum import Enum

import tiktoken


class ContentType(str, Enum):
    AST_CODE = "ast_code"
    TEST_LOG = "test_log"
    TABULAR_DATA = "tabular_data"
    PROSE_MARKDOWN = "prose_markdown"
    UNKNOWN = "unknown"


class ContentRouter:
    """Classifies content and determines optimal token reduction strategy."""

    def __init__(self, default_encoding: str = "cl100k_base"):
        self.default_encoding = default_encoding
        try:
            self._tokenizer = tiktoken.get_encoding(default_encoding)
        except Exception:  # noqa: BLE001
            self._tokenizer = None

    def count_tokens(self, text: str, model: str | None = None) -> int:
        """Counts tokens accurately using tiktoken BPE, with fallback."""
        if not text:
            return 0
        try:
            enc = tiktoken.get_encoding(model or self.default_encoding)
            return len(enc.encode(text))
        except Exception:  # noqa: BLE001
            return max(1, len(text) // 4)

    def classify(self, content: str, filename: str | None = None) -> ContentType:
        """Classifies content into structural categories."""
        if not content or not content.strip():
            return ContentType.UNKNOWN

        lines = content.strip().splitlines()
        first_line = lines[0].strip()

        # AST Code heuristic
        if filename and filename.endswith(
            (".py", ".ts", ".js", ".rs", ".go", ".cpp", ".c", ".java")
        ):
            return ContentType.AST_CODE
        if any(
            kw in first_line
            for kw in [
                "def ",
                "class ",
                "import ",
                "from ",
                "fn ",
                "pub fn",
                "interface ",
                "type ",
            ]
        ):
            return ContentType.AST_CODE

        # Test log heuristic
        if any(
            "FAILED" in l
            or "PASSED" in l
            or "=== FAILURES ===" in l
            or "error[E" in l
            or "FAIL " in l
            for l in lines[:15]
        ):
            return ContentType.TEST_LOG

        # Tabular / JSON heuristic
        if first_line.startswith(("[", "{")) and lines[-1].strip().endswith(("]", "}")):
            return ContentType.TABULAR_DATA

        return ContentType.PROSE_MARKDOWN
