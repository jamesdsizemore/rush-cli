"""TOON v4.1 (Token-Oriented Object Notation) table encoder."""

from typing import Any


class ToonEncoder:
    """Serializes lists of dictionaries into ultra-compact pipe-delimited tables."""

    @staticmethod
    def encode(data: list[dict[str, Any]]) -> str:
        if not data:
            return ""

        # Extract all unique keys preserving order
        keys: list[str] = []
        for item in data:
            for k in item:
                if k not in keys:
                    keys.append(k)

        # Header row
        header = "|" + "|".join(keys) + "|"
        separator = "|" + "|".join("---" for _ in keys) + "|"

        rows: list[str] = [header, separator]

        for item in data:
            row_cells = []
            for k in keys:
                val = item.get(k, "")
                val_str = str(val).replace("|", "\\|").replace("\n", " ")
                row_cells.append(val_str)
            rows.append("|" + "|".join(row_cells) + "|")

        return "\n".join(rows)


def encode_toon(data: list[dict[str, Any]]) -> str:
    return ToonEncoder.encode(data)
