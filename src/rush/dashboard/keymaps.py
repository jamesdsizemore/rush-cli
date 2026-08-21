"""Keyboard navigation controller and keybinding handler for Textual TUI."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class KeybindingAction:
    key: str
    action_name: str
    description: str


DEFAULT_KEYBINDINGS = [
    KeybindingAction(key="q", action_name="quit", description="Exit Rush TUI"),
    KeybindingAction(key="j", action_name="cursor_down", description="Navigate down one row"),
    KeybindingAction(key="k", action_name="cursor_up", description="Navigate up one row"),
    KeybindingAction(key="enter", action_name="select_row", description="Inspect selected finding"),
    KeybindingAction(key="f", action_name="apply_fix", description="Trigger automated fix for selected finding"),
    KeybindingAction(key="r", action_name="refresh", description="Rerun quality suite"),
    KeybindingAction(key="slash", action_name="focus_filter", description="Focus search filter input"),
]


class KeymapManager:
    """Manages customizable TUI keyboard mappings."""

    def __init__(self, keybindings: list[KeybindingAction] | None = None) -> None:
        self.bindings = keybindings or list(DEFAULT_KEYBINDINGS)

    def get_action_for_key(self, key: str) -> str | None:
        for b in self.bindings:
            if b.key == key:
                return b.action_name
        return None
