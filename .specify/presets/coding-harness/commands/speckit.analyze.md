## Coding-Harness Analysis Addendum

In addition to the core artifact analysis, report as blocking findings:

- any conflict with an applicable `AGENTS.md` rule or the project Constitution;
- missing Gherkin or executable tests for changed behavior;
- Controller-to-Repository, Tool-to-DB, Domain-to-framework, or other reverse layer dependencies;
- inconsistent business terminology across frontend, API, Service, persistence, and CLI;
- missing failure, permission, idempotency, compatibility, or sensitive-data behavior;
- tasks that modify README without explicit user authorization.

Do not recommend implementation while any blocking finding remains unresolved.
