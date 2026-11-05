# Latest team baseline

Branch: `codex/v1.1-longrun-reliability`
Project directory: `alternative-frame/v1.1-experimental`

This branch publishes the latest long-horizon reliability fixes, task workspace isolation, API accounting, Windows tool execution fixes, UI limits and regression tests.

## Getting started

Fetch origin and check out this branch in a clean checkout. Run `python ui.py` from the project directory, or use the Chinese-named UI launcher batch file. Python 3 with tkinter is required. Configure your own API endpoint, model and key in the UI. No shared API credentials are included.

## Validation and boundaries

The local working tree regression recorded 190 passes and one requirements-document acceptance failure. The local requirements.md was a historical generated task document and is deliberately excluded from this publication; the repository baseline document is retained. These local results are not a fresh-clone certification of this commit. The reliability-related regression subset passed 64 tests.

A live run generated a research evidence management web application and its 25 tests passed independently. Browser interaction acceptance remains incomplete. Model semantic acceptance is not equivalent to verified browser interaction. No universal task completion guarantee is made.

Runtime directories, local API configurations, generated calculator/research products, caches, local evidence and changes to v0.1 are excluded. Original competition tags are unchanged. Team members should branch from this baseline for new work and keep their existing work before switching branches.
