# Testing

The canonical strategy is [Developer testing guide](developer/testing-guide.md). Rush separates unit contracts, native parser fixtures, fake-process invocation, routing, CLI, real stdio MCP, bounded installed-engine, packaging, clean-clone, and remote-CI evidence.

A broad catalog does not justify an all-runtime test image. Fixture tests own parser behavior; selected real engines prove representative integration.
