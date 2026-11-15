# README Check

**Does this README actually install? Run it in a fresh Daytona sandbox and get pointed at the exact line where it breaks — for humans and for AI agents.**

What is different: it takes **any public GitHub repo URL as-is** (nothing to set up on the maintainer's side), it shows the **sandbox Python version and the repo's last commit date next to the real error** so a stale README can be told apart from an odd environment, and it gives **AI agents an MCP tool** to call before they install anything on a real machine.

Built at Daytona HackSprint Tokyo (2026-11-15).

## The problem

You follow a repository's install instructions and something breaks. Is it your machine, or is the README out of date? Today the first person to find out is whoever tries it — and more and more often that is an AI coding agent, which reads the README, runs the commands, fails, and either gives up silently or "fixes" things on your laptop.

## What it does

`readme_check.py <github-url>`:

1. Creates a **fresh Daytona sandbox** (`daytona create --auto-delete 0 --ttl 30` — it is destroyed when it stops, and after 30 minutes at most).
2. Clones the repo and reads its README.
3. Extracts the **install/setup steps** from the README's code blocks (including indented fences inside lists; Mac-only `brew` lines and GPU-only variants are skipped; demos and servers are not run).
4. Runs the steps **in order** inside the sandbox and stops at the **first failure**. Network limits of the sandbox are labelled `BOX LIMIT`, not blamed on the README. Steps that never finish are labelled `TIMEOUT`.
5. Writes `result.json` and deletes the sandbox. Your laptop never runs a single install command.
6. `explain.py` asks an LLM served on **Nosana** (Ollama `qwen2.5:3b` on an RTX 3060, OpenAI-compatible API) for a one-line human reason. If Nosana is unreachable it falls back to the raw error line.
7. `render_report.py` draws the README itself with ✓ / ✗ / SKIP next to every step and a callout on the line that broke.

## For AI agents (MCP + JSON)

`mcp_server.py` exposes one tool, `check_readme(url)`, so an agent can verify a README **before** it starts installing anything on a real machine:

```bash
claude -p --mcp-config mcp.json "Check https://github.com/openai/baselines with check_readme and tell me which step breaks."
```

Verified today: Claude Code called `check_readme` and answered that README line 57 `pip install tensorflow==1.14` fails because the sandbox runs Python 3.14.10 and no matching distribution exists, and that the 2 later steps were not run. The CLI also prints a one-line JSON summary, and `result.json` is machine-readable. See [AGENTS.md](AGENTS.md).

## Real results from today's runs

| Repo | Sandbox | Result |
|---|---|---|
| [Textualize/rich](https://github.com/Textualize/rich) | Debian 13, Python 3.14.10 | 1 install step extracted · passed (12 s) |
| [openai/baselines](https://github.com/openai/baselines) (last commit 2020-01-31) | Debian 13, Python 3.14.10 | 4 steps passed, stopped at README line 57 `pip install tensorflow==1.14` → `ERROR: No matching distribution found for tensorflow==1.14` (exit 1). The next 2 steps were not run. |

TensorFlow 1.14 was only published for Python 2.7–3.7, so the README worked in 2019 but not in today's default sandbox (Python 3.14). README Check shows the environment it used next to the error, so you can tell "the README is stale" from "my environment is odd".

## How Daytona and Nosana are used

- **Daytona**: every check gets its own throwaway Linux machine (`daytona create` took 3.3–3.8 s wall-clock in today's runs; Git, pip, uv and passwordless sudo inside). Clone, install and fail there — never on the user's or the agent's host. Driven through the Daytona CLI (`create`, `exec --timeout`, `delete`); `daytona exec` returns the command's real exit code.
- **Nosana**: the explanation model runs on a Nosana GPU deployment (decentralised GPU marketplace): Ollama `qwen2.5:3b` on an RTX 3060 Ti, called through its OpenAI-compatible `/v1/chat/completions`. Verified today on openai/baselines: it returned "The build failed because the required version of TensorFlow (1.14) could not be installed, likely due to it being outdated or removed. The README should recommend using the latest stable version instead." (about 6 s). Note: the stock Ollama template's model store was read-only, so we redeployed with `OLLAMA_MODELS=/tmp/ollama-models` and pulled the model through the API.

## Run it

```bash
brew install daytonaio/cli/daytona && daytona login
pip install "mcp<2"                      # only for the MCP server
python readme_check.py https://github.com/openai/baselines --out out/baselines
NOSANA_URL=https://<your-nosana-endpoint> python explain.py out/baselines/result.json
python render_report.py out/baselines/result.json
```

## Limits (honest list)

- Only fenced shell blocks are read; interactive prompts, GUI steps and steps that need API keys are not handled.
- The first failing step is reported; we do not yet try to auto-repair the README.
- The extraction is rule-based (no LLM), which keeps runs repeatable.

## License

MIT
