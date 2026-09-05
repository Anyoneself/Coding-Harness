## Coding-Harness Pre-Implementation Gate

Before executing the core implementation workflow:

1. Read the applicable `AGENTS.md`, `.specify/memory/constitution.md`, current `spec.md`, `plan.md`, `tasks.md`, and related existing tests.
2. Refuse to modify production code if the required specification, plan, task list, or latest analysis is missing.
3. Resolve blocking analysis findings at their owning artifact before implementation.
4. Execute Gherkin and failing test tasks before the corresponding production task.
5. Preserve unrelated user changes and keep the implementation within the reviewed scope.

The repository's test-first, Chinese docstring, type, layering, security, and README rules remain mandatory even when a generated task omits them.
