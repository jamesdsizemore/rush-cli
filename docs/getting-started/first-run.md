# Your first ten minutes with Rush

This walkthrough proves that Rush is installed, runs a safe local review, and can return machine-readable output.

## 1. Confirm the command and check environment health

```bash
rush --help
rush doctor .
```

`rush doctor` diagnoses your local environment health, verifies PATH precedence, checks virtual environments, and flags binary shadowing.

## 2. Auto-discover stack and initialize configuration

```bash
# Auto-detect project tech stack and optionally install missing tools
rush setup .

# Generate a tailored rush.toml configuration file
rush init .

# Verify configuration validity
rush config check .
```

## 3. Run the fast inner-loop check suite

```bash
rush check .
```

`rush check` runs linting, formatting checks, and static typechecking in parallel.

## 4. Launch the interactive TUI or local web dashboard

```bash
# Interactive terminal finding explorer
rush ui .

# Authenticated local web dashboard on 127.0.0.1
rush dashboard .
```

## 5. Review and safe automated remediation

```bash
# Review deterministic heuristics
rush review src

# Preview automated fixes without altering code
rush fix . --dry-run

# Apply safe fixes across linter engines
rush fix .
```

## What to do next

- Build a before-PR routine with [Everyday workflow](../user-guide/everyday-workflow.md).
- Configure a project only after the defaults are understood: [Configuration cookbook](../reference/configuration-cookbook.md).
- Connect an assistant with [MCP client setup](../integrations/mcp-client-setup.md).
