# For AI agents

README Check tells you, before you install anything on a real machine, whether a repository's README install steps actually work — by running them in a fresh, throwaway Daytona sandbox.

## Call it

- MCP (stdio): `python mcp_server.py` → tool `check_readme(url: str) -> str` (JSON).
- CLI: `python readme_check.py <github-url> --out <dir>` → prints one JSON line; full detail in `<dir>/result.json`.

## Output (JSON)

| field | meaning |
|---|---|
| `status` | `passed` / `failed` / `clone_failed` |
| `extracted` | number of install/setup steps found in the README |
| `steps[]` | `{line, cmd, status: pass/fail/skip/timeout/box_limit, exit_code}` in README order |
| `first_failure` | `{line, cmd, exit_code, error_line}` — the README line that broke and the real error text |
| `box_python`, `last_commit` | sandbox Python version and the repo's last commit date (tells "stale README" from "odd environment") |
| `reason`, `reason_by` | one-line explanation (LLM on Nosana) or the raw error line as fallback |
| `sandbox_deleted` | the sandbox is deleted after every run |

## How to use the answer

- `failed` → do not run the README as-is on the user's machine; report `first_failure.line` and `error_line`, and adapt (e.g. pin an older Python) before installing.
- `box_limit` steps are sandbox network limits, not README bugs.
- `timeout` steps did not finish in 240 s; treat as unknown.
