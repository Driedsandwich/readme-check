#!/usr/bin/env python3
"""MCP server exposing check_readme(url) so an AI agent can verify a repo's README install steps
in a fresh Daytona sandbox before it starts installing anything itself.

Run (stdio):  python mcp_server.py
Claude Code (one-off, no settings change):  claude -p --mcp-config mcp.json "..."
"""
import json, os, subprocess, sys, tempfile

from mcp.server.fastmcp import FastMCP

HERE = os.path.dirname(os.path.abspath(__file__))
mcp = FastMCP("readme-check")


@mcp.tool()
def check_readme(url: str) -> str:
    """Run the README install steps of a public GitHub repo in a fresh Daytona sandbox.
    Returns JSON: status (passed/failed), steps extracted, the first failing step (README line,
    command, exit code, real error line), sandbox Python version, repo last commit date."""
    out = tempfile.mkdtemp(prefix="readme-check-")
    subprocess.run([sys.executable, os.path.join(HERE, "readme_check.py"), url, "--out", out],
                   capture_output=True, text=True, timeout=1800)
    path = os.path.join(out, "result.json")
    if os.environ.get("NOSANA_URL"):
        subprocess.run([sys.executable, os.path.join(HERE, "explain.py"), path], capture_output=True, text=True, timeout=120)
    r = json.load(open(path))
    keep = {k: r.get(k) for k in ("url", "status", "extracted", "box_python", "last_commit", "first_failure",
                                   "reason", "reason_by", "sandbox_deleted")}
    keep["steps"] = [{"line": s.get("line"), "cmd": s.get("cmd"), "status": s.get("status"),
                      "exit_code": s.get("exit_code")} for s in r.get("steps", [])]
    return json.dumps(keep, ensure_ascii=False)


if __name__ == "__main__":
    mcp.run()
