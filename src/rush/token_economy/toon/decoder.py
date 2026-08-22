"""TOON v4.1 table decoder deserializing pipe tables back to dictionaries."""

from typing import Any


class ToonDecoder:
    """Deserializes TOON pipe-delimited tables back to list of dicts."""

    @staticmethod
    def decode(toon_str: str) -> list[dict[str, Any]]:
        lines = [l.strip() for l in toon_str.strip().splitlines() if l.strip()]
        if len(lines) < 3:
            return []

        # Parse header
        raw_header = lines[0].strip("|").split("|")
        headers = [h.strip() for h in raw_header]

        results: list[dict[str, Any]] = []

        # Skip separator line at lines[1]
        for line in lines[2:]:
            cells = line.strip("|").split("|")
            row_dict: dict[str, Any] = {}
            for i, h in enumerate(headers):
                cell_val = (
                    cells[i].replace("\\|", "|").strip() if i < len(cells) else ""
                )
                row_dict[h] = cell_val
            results.append(row_dict)

        return results


def decode_toon(toon_str: str) -> list[dict[str, Any]]:
    return ToonDecoder.decode(toon_str)
