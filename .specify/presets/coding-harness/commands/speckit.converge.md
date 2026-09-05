## Coding-Harness Convergence Addendum

The implementation is not converged unless:

- every changed behavior maps from a specification requirement to a Gherkin scenario and executable passing test;
- no applicable `AGENTS.md` or Constitution rule is violated;
- affected frontend, API, Service, persistence, CLI, example, and architecture contracts are synchronized;
- relevant tests, the full unit/integration suite, `ruff check .`, and applicable frontend checks have recorded outcomes;
- failures, permissions, idempotency, compatibility, and sensitive-data handling match the specification;
- unrelated working-tree changes remain untouched.
