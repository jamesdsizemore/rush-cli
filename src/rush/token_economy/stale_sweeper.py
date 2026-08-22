"""Multi-turn conversation history stale read sweeper (TokenTamer)."""

from typing import Any


class StaleSweeper:
    """Collapses older turns' verbose file reads into 1-line signatures while preserving current turn."""

    def __init__(self, keep_recent_turns: int = 1):
        self.keep_recent_turns = keep_recent_turns

    def sweep_history(self, turns: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Prunes previous turns' file contents while keeping recent turns intact."""
        if len(turns) <= self.keep_recent_turns:
            return turns

        swept: list[dict[str, Any]] = []
        stale_cutoff = len(turns) - self.keep_recent_turns

        for idx, turn in enumerate(turns):
            if idx < stale_cutoff:
                # Collapse large text payload in stale turn
                turn_copy = dict(turn)
                content = str(turn_copy.get("content", ""))
                if len(content) > 300:
                    lines = content.splitlines()
                    summary_line = f"<!-- stale_read: collapsed {len(lines)} lines ({len(content)} bytes) -->\n{lines[0] if lines else ''}..."
                    turn_copy["content"] = summary_line
                    turn_copy["stale_pruned"] = True
                swept.append(turn_copy)
            else:
                swept.append(turn)

        return swept
