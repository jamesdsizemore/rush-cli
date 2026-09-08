"""Memory maintenance must be classified as a canonical state mutation."""

from rush.governance.public_operations import build_operations_inventory


def test_memory_maintenance_inventory_uses_mutating_memory_implementation():
    operation = next(
        item
        for item in build_operations_inventory()
        if item.cli_command == "memory maintain"
    )
    assert operation.effect_class == "stateful-mutation"
    assert operation.canonical_impl == "rush.tools.memory:MemoryTool"
