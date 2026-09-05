## Coding-Harness Planning Rules

- Treat `AGENTS.md` and `.specify/memory/constitution.md` as mandatory planning gates.
- Inspect the real repository structure and reuse its Controller, Service, Domain, Repository, DB, CLI, Agent, Tool, and Infrastructure boundaries.
- Do not retain generic sample directories in the completed plan.
- Define the Gherkin scenarios, executable test layers, failure paths, static checks, and end-to-end validation commands before implementation tasks are generated.
- Identify every affected contract across frontend, HTTP API, Service DTO, persistence, CLI, examples, and architecture documentation.
- New dependencies and abstractions require a current, concrete need and an explicit justification.
