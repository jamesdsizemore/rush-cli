"""Snapshot check tool."""

from .quality import GuardedQualityTool


class SnapshotTool(GuardedQualityTool):
    name = "snapshot"
    required_option = "accept"
    default_reason = "snapshot baselines are never updated by default"

    @property
    def mcp_description(self):
        return "Check snapshots; updates require --accept."
