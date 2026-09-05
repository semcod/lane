# Internal dependency updates

This repository owns its dependency configuration and this guide, following the repository ownership principle in [wellmanifest/docs](https://github.com/wellmanifest/docs/blob/f64de5806577769672ebc1730d2e144b4c7671ec/README.md). The checker belongs to [semcod/goal](https://github.com/semcod/goal/blob/84f18540d14c24cc8ff5b7f202d2874344779ecc/docs/internal-dependencies.md).

## Python and installation

Application support remains Python >=3.10. Source inspection found no Goal imports or executable invocation in application Python code. Goal's old declarations moved to an `automation` dependency group requiring Python >=3.12, so updating release tooling does not remove Python 3.10 application support.

```sh
uv sync --locked --extra dev --python 3.10
uv run --no-sync python -m pytest -q
UV_PROJECT_ENVIRONMENT=.venv-automation uv sync --locked --group automation --python 3.12
```

The automation command uses a separate environment. Synchronize the application environment again after merging tested dependency updates.

## Daily checks

[Dependabot](../.github/dependabot.yml) checks the explicit costs, Goal, pfix, clickmd and code2llm catalog daily, including weekends, and groups updates into one PR. It includes transitive packages and may widen constraints when necessary. This is a bounded catalog, not discovery of every internal package. Local/Git sources and other packages need separate review.

[Freshness CI](../.github/workflows/internal-dependency-freshness.yml) uses released Goal 2.2.0 to compare uv.lock with the highest published stable three-part versions of the catalog packages actually used here. It has read-only repository permissions, runs daily/manually/on dependency PRs, and retains JSON evidence. Registry and resolution errors remain visible. An audit does not prove a deployed environment has installed the new versions.

[Locked CI](../.github/workflows/ci.yml) installs the dev extra from uv.lock and runs the full suite, 95% coverage gate, mypy, Ruff and examples on Python 3.10, 3.11, 3.12 and 3.13. A permissive version declaration alone does not refresh the lockfile; update creation, testing, merge and installation are separate steps.

## Delivery

The registry targets observed on 2026-09-05 are costs 0.2.0, Goal 2.2.0, pfix 0.1.79, clickmd 1.1.15 and code2llm 0.5.176. PR and Actions checks hold the test results; the [ecosystem rollout history](https://github.com/semcod/costs/tree/main/docs/dependencies) belongs to costs. Reports and instructions are versioned in repository docs, rather than temporary machine directories.

The existing CI retains its 95% coverage gate. Regression tests exercise real temporary Git histories, optional Koru failures, and auto-mode dry-run/synchronization boundaries. Bug-fix counting now combines keyword filters in one Git query and counts each commit once, preventing densities above 100% caused by repeated keywords. `pytest-cov` is declared in the dev extra so the coverage gate can also run from the lockfile.

The existing CI now uses uv.lock for all its gates. Its previous pip installation selected Ruff 0.16.6 while the lockfile contained 0.15.17, producing different lint rules from local checks. The lockfile is the shared source of dependency versions; updates to third-party tools need their own tested lockfile changes.
