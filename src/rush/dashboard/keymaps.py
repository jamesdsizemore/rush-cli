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
    KeybindingAction(
        key="j", action_name="cursor_down", description="Navigate down one row"
    ),
    KeybindingAction(
        key="k", action_name="cursor_up", description="Navigate up one row"
    ),
    KeybindingAction(
        key="down", action_name="cursor_down", description="Navigate down one row"
    ),
    KeybindingAction(
        key="up", action_name="cursor_up", description="Navigate up one row"
    ),
    KeybindingAction(
        key="enter", action_name="select_row", description="Inspect selected finding"
    ),
    KeybindingAction(
        key="tab", action_name="next_project", description="Switch to next project"
    ),
    # P69-06c: Phase 66 §3.8 names F2 as the dedicated project-selector key,
    # freeing Tab for pane cycling -- but that remapping depends on real F2/
    # Shift+Tab escape-sequence decoding in `terminal_input.py`, which is not
    # in this packet's allowed files (and `tab` still backs the real,
    # passing `test_keyboard_project_switch` PTY test). F2 is added here as
    # an additional binding for the same action, so it already works once a
    # future packet adds that decoding; `tab` keeps its current behavior for
    # now rather than silently losing project switching in the meantime.
    KeybindingAction(
        key="f2", action_name="next_project", description="Open project selector"
    ),
    KeybindingAction(
        key="f3", action_name="toggle_git_view", description="Switch section"
    ),
    KeybindingAction(
        key="?", action_name="show_help", description="Show current key bindings"
    ),
    KeybindingAction(
        key="/", action_name="focus_filter", description="Search/filter findings"
    ),
    KeybindingAction(
        key="escape",
        action_name="cancel",
        description="Back / dismiss / decline",
    ),
    KeybindingAction(
        key="s",
        action_name="start_scan",
        description="Start a full scan (reviewed before running)",
    ),
    KeybindingAction(
        key="c", action_name="cancel_scan", description="Cancel the running scan"
    ),
    KeybindingAction(
        key="r",
        action_name="rescan",
        description="Rescan last run (reviewed before running)",
    ),
    # P69-06c: rebound from "h" (Phase 66 §3.8 reserves lowercase h for
    # collapse, part of the hierarchical Map navigation this packet does not
    # build -- see module docstring note above); no test exercises the old
    # lowercase binding.
    KeybindingAction(
        key="H",
        action_name="prepare_handoff",
        description="Review and send an agent handoff",
    ),
    KeybindingAction(
        key="a",
        action_name="cycle_agent",
        description="Cycle Setup/Agents target for handoff",
    ),
    KeybindingAction(
        key="m",
        action_name="toggle_memory",
        description="Toggle memory/token-gain HUD",
    ),
    KeybindingAction(
        key="y",
        action_name="confirm_grant",
        description="Confirm the pending reviewed action",
    ),
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
