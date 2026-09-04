# Repository-Grounded Feature Task Template

Use this as the shape of a task that gives one coding agent a complete, independently executable repository change. Fill every included section with repository-verified facts. Omit a whole section only when it does not apply to that task. Do not leave placeholders, generic process instructions, discovery work, approval gates, or references to another task for missing behavior.

```markdown
Implement `<one named feature or repository change>` in `<repository name>` in the current working directory.

Read `<binding repository instructions>` and `<binding specification or design document>` first; both are binding. Read `<user-facing documentation>` when the task changes user-visible behavior.

# Feature: `<precise outcome>`

`<One sentence defining the result this task must deliver.>`

## Required behavior

1. `<Exact externally observable behavior, including inputs, outputs, defaults, and unchanged behavior.>`
2. `<Exact matching, parsing, state, security, containment, compatibility, or error behavior.>`
3. `<Exact edge cases and their required result.>`
4. `<Exact behavior that remains unchanged.>`

## Deliverables

- `<Exact production files and symbols to change or create.>`
- `<Exact documentation files and the claims they must add, replace, or preserve.>`
- `<Exact test files, test names, fixtures, inputs, and assertions.>`
- `<Exact artifact, migration, configuration, registry, route, or compatibility deliverable, when required.>`

## Constraints

- `<Exact file formats, interfaces, dependencies, behaviors, or scope that must remain unchanged.>`
- `<Exact prohibited work.>`
- `<Exact safety, testing, network, environment, Git, or release restrictions.>`

## Checks to run before reporting

All of these must pass:

`<exact command>`
`<exact command>`
`<exact command>`

## Completion

The task is complete only when `<exact behavior exists>`, `<exact tests and checks pass>`, and only `<literal allowed paths>` were changed.

## Handoff

`<Exact required report file, report contents, and final-message requirement; omit this section when no handoff artifact is required.>`
```

Every behavior item must be testable. Every deliverable must name literal files and symbols. Every test requirement must name concrete scenarios and assertions. Every check must be an executable command with a pass requirement. The task must contain enough repository facts that the coding agent does not choose behavior, scope, dependencies, files, tests, or completion criteria itself.
