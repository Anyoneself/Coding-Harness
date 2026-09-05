## Coding-Harness Mandatory Task Rules

The core statement that tests are optional does not apply to this repository.

- Every changed business behavior must first have a Gherkin task under `tests/features/`.
- Every Gherkin scenario must map to an executable unit, integration, or end-to-end test task.
- Place test tasks before production implementation tasks and require the new test to fail for the expected missing behavior before implementation.
- Include success, relevant boundary, and explicit failure-path tests for every user story.
- Include exact repository paths and preserve Controller, Service, Domain, Repository, DB, CLI, Agent, Tool, Infrastructure, and frontend ownership.
- Add final tasks for affected tests, `python -m unittest discover -s tests -v`, `ruff check .`, applicable frontend checks, documentation synchronization, and `$speckit-converge`.
- Do not add a README task unless the user explicitly requested a release or README change.
