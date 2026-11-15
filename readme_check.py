#!/usr/bin/env python3
"""README Check: run a repo's README install steps in a fresh Daytona sandbox and point at the first line that breaks.

Usage:
  python readme_check.py https://github.com/owner/repo [--out out_dir] [--keep]

Uses the Daytona CLI (`daytona login` once). No API key is handled by this tool.
"""
import argparse, datetime, json, os, re, shlex, subprocess, sys, time

DAYTONA = os.environ.get("DAYTONA_BIN", "daytona")
REPO_DIR = "/home/daytona/repo"
STEP_TIMEOUT = int(os.environ.get("README_CHECK_STEP_TIMEOUT", "240"))
INSTALL = re.compile(r"(\binstall\b|^git\s+clone|^(sudo\s+)?(uv|conda|poetry|pipenv)\s+(sync|create|env|venv|install)|^python3?\s+-m\s+venv|^cd\s|^make(\s|$)|^python3?\s+setup\.py)")
TIMEOUT_MARK = re.compile(r"(PROCESS_EXECUTION_TIMEOUT|command execution timeout|timed out after)")

NET_LIMIT = re.compile(r"(Temporary failure in name resolution|Could not resolve host|Name or service not known|"
                       r"Network is unreachable|Connection timed out|Failed to establish a new connection|"
                       r"403 Forbidden.*proxy|ERR_NETWORK|Could not connect to)", re.I)
CMD_START = re.compile(r"^(sudo\s+)?(pip3?|python3?|py|git|npm|npx|pnpm|yarn|uv|conda|apt(-get)?|make|cd|"
                       r"poetry|pipenv|cargo|go|node|bash|sh|export|mkdir|cp|mv|wget|curl|pytest|tox|"
                       r"docker|julia|R|gem|bundle|mvn|gradle)\b")
SKIP_LINE = re.compile(r"^(brew\s|open\s|code\s|start\s|choco\s|winget\s|xcode-select)")
GPU_HINT = re.compile(r"(cuda|gpu|nvidia|cudnn)", re.I)


def sh(args, timeout=None):
    p = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    return p.returncode, p.stdout, p.stderr


def box_exec(name, cmd, timeout=STEP_TIMEOUT, cwd=None):
    pre = "export DEBIAN_FRONTEND=noninteractive PIP_NO_INPUT=1 PIP_DISABLE_PIP_VERSION_CHECK=1; "
    inner = pre + (f"cd {shlex.quote(cwd)} 2>/dev/null; {cmd}" if cwd else cmd)
    t0 = time.time()
    try:
        rc, out, err = sh([DAYTONA, "exec", name, "--timeout", str(timeout), "--",
                           "bash", "-lc", inner], timeout=timeout + 30)
    except subprocess.TimeoutExpired:
        return 124, "", f"timed out after {timeout}s", round(time.time() - t0, 1)
    return rc, out, err, round(time.time() - t0, 1)


def extract_steps(readme):
    """Pull shell commands out of fenced code blocks (indented fences too). Skip Mac-only and GPU variants."""
    steps, lines = [], readme.splitlines()
    i, n = 0, len(lines)
    while i < n:
        m = re.match(r"^(\s*)(```|~~~)\s*([\w+-]*)", lines[i])
        if not m:
            i += 1
            continue
        indent, fence, lang = m.group(1), m.group(2), (m.group(3) or "").lower()
        start = i
        i += 1
        block = []
        while i < n and not re.match(r"^\s*" + re.escape(fence), lines[i]):
            block.append((i + 1, lines[i][len(indent):] if lines[i].startswith(indent) else lines[i].strip()))
            i += 1
        i += 1
        if lang and lang not in ("", "bash", "sh", "shell", "console", "zsh", "shell-session", "text", "sh-session"):
            continue
        for ln, raw in block:
            line = raw.strip()
            if line.startswith("$ "):
                line = line[2:]
            if not line or line.startswith("#") or line.startswith(">>>"):
                continue
            if SKIP_LINE.match(line) or not CMD_START.match(line):
                continue
            if GPU_HINT.search(line):
                continue  # prefer CPU variants
            if not INSTALL.search(line):
                continue  # install/setup steps only (skip demos, servers, usage examples)
            steps.append({"line": ln, "cmd": line, "block_start": start + 1})
    return steps


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("url")
    ap.add_argument("--out", default="out")
    ap.add_argument("--keep", action="store_true")
    ap.add_argument("--max-steps", type=int, default=12)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    slug = re.sub(r"[^a-z0-9]+", "-", a.url.rstrip("/").split("/")[-1].lower())[:20]
    name = f"rc-{slug}-" + datetime.datetime.now().strftime("%H%M%S") + f"-{os.getpid() % 1000}"
    res = {"url": a.url, "sandbox": name, "started": datetime.datetime.now().isoformat(timespec="seconds"), "steps": []}
    t0 = time.time()
    rc, out, err = sh([DAYTONA, "create", "--name", name, "--auto-delete", "0", "--ttl", "30"], timeout=180)
    if rc != 0:
        print("create failed:", err[-500:], file=sys.stderr)
        sys.exit(2)
    res["create_seconds"] = round(time.time() - t0, 1)
    try:
        rc, out, err, secs = box_exec(name, f"git clone --depth 1 {shlex.quote(a.url)} {REPO_DIR}", timeout=180)
        res["clone"] = {"exit_code": rc, "seconds": secs}
        if rc != 0:
            res["status"] = "clone_failed"
            res["error_line"] = ((err or out).strip().splitlines() or [""])[-1]
            return
        box_exec(name, "echo 'APT::Get::Assume-Yes \"true\";' | sudo tee /etc/apt/apt.conf.d/90assumeyes >/dev/null 2>&1; true", timeout=30)
        _, env_out, _, _ = box_exec(name, "python3 --version; uname -s -m; git -C %s log -1 --format=%%cs" % REPO_DIR, timeout=60)
        env = env_out.strip().splitlines()
        res["box_python"] = env[0] if env else ""
        res["box_os"] = env[1] if len(env) > 1 else ""
        res["last_commit"] = env[2] if len(env) > 2 else ""
        _, readme, _, _ = box_exec(name, f"cd {REPO_DIR} && cat $(ls README.md readme.md Readme.md README.rst README.txt README 2>/dev/null | head -1)", timeout=60)
        res["readme"] = readme
        steps = extract_steps(readme)[: a.max_steps]
        res["extracted"] = len(steps)
        def _norm(u):
            u = u.strip().rstrip("/")
            u = re.sub(r"\.git$", "", u)
            return "/".join(u.lower().split("/")[-2:])
        self_clone = any(s["cmd"].startswith("git clone") and _norm(a.url) in _norm(s["cmd"].split()[2] if len(s["cmd"].split()) > 2 else "") for s in steps)
        cwd = "/home/daytona/work" if self_clone else REPO_DIR
        if self_clone:
            box_exec(name, "mkdir -p /home/daytona/work", timeout=30)
        res["start_dir"] = cwd
        failed = False
        for s in steps:
            if failed:
                res["steps"].append({**s, "status": "skip", "note": "not run (stopped at first failure)"})
                continue
            cmd = s["cmd"]
            if cmd.startswith("cd "):
                target = cmd[3:].strip()
                cwd = target if target.startswith("/") else os.path.normpath(os.path.join(cwd, target))
                res["steps"].append({**s, "status": "pass", "exit_code": 0, "seconds": 0, "note": "cd"})
                continue
            rc, out, err, secs = box_exec(name, cmd, cwd=cwd)
            tail = (out + "\n" + err).strip().splitlines()[-15:]
            err_line = next((l for l in reversed(tail) if re.search(r"(error|Error|ERROR|not found|No matching)", l)), tail[-1] if tail else "")
            st = {**s, "exit_code": rc, "seconds": secs, "log_tail": tail, "error_line": err_line}
            if rc == 0:
                st["status"] = "pass"
            elif TIMEOUT_MARK.search(out + err) or rc == 124:
                st["status"] = "timeout"
                st["note"] = f"did not finish within {STEP_TIMEOUT}s"
                st["error_line"] = f"timed out after {STEP_TIMEOUT}s"
            elif NET_LIMIT.search(out + err):
                st["status"] = "box_limit"
                st["note"] = "sandbox network limit, not a README bug"
            else:
                st["status"] = "fail"
                failed = True
                res["first_failure"] = {"line": s["line"], "cmd": cmd, "exit_code": rc, "error_line": err_line}
            res["steps"].append(st)
        res["status"] = "failed" if failed else "passed"
    finally:
        finish(res, a, name)


def finish(res, a, name):
    if not a.keep:
        rc, _, _ = sh([DAYTONA, "delete", name], timeout=120)
        res["sandbox_deleted"] = rc == 0
    res["finished"] = datetime.datetime.now().isoformat(timespec="seconds")
    path = os.path.join(a.out, "result.json")
    with open(path, "w") as f:
        json.dump(res, f, ensure_ascii=False, indent=2)
    passed = sum(1 for s in res["steps"] if s["status"] == "pass")
    print(json.dumps({"url": res["url"], "status": res.get("status"), "extracted": res.get("extracted"),
                      "passed": passed, "first_failure": res.get("first_failure"), "box_python": res.get("box_python"),
                      "last_commit": res.get("last_commit"), "result": path}, ensure_ascii=False))
    return res


if __name__ == "__main__":
    main()
