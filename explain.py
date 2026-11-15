#!/usr/bin/env python3
"""Add a one-line human reason to result.json using an LLM served on Nosana (Ollama, OpenAI-compatible API).

Usage:
  NOSANA_URL=https://<your-nosana-deployment-endpoint> python explain.py out/baselines/result.json

Falls back to the raw error line when the endpoint is not reachable, so the demo never blocks on it.
"""
import json, os, sys, urllib.request

MODEL = os.environ.get("NOSANA_MODEL", "qwen2.5:3b")


def ask(base, prompt, timeout=40):
    body = json.dumps({"model": MODEL, "temperature": 0, "max_tokens": 60,
                       "messages": [{"role": "system", "content": "You explain build failures in one short plain-English sentence. No markdown."},
                                    {"role": "user", "content": prompt}]}).encode()
    req = urllib.request.Request(base.rstrip("/") + "/v1/chat/completions", data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        j = json.load(r)
    return j["choices"][0]["message"]["content"].strip().splitlines()[0]


def main():
    path = sys.argv[1]
    res = json.load(open(path))
    ff = res.get("first_failure")
    if not ff:
        print("no failure to explain")
        return
    step = next((s for s in res["steps"] if s.get("line") == ff["line"]), {})
    prompt = (f"A README install step failed in a fresh Linux sandbox ({res.get('box_python')}). "
              f"The repository was last updated on {res.get('last_commit')}.\n"
              f"Command: {ff['cmd']}\nExit code: {ff['exit_code']}\n"
              f"Last log lines:\n" + "\n".join(step.get("log_tail", [])[-8:]) +
              "\nIn one sentence, why did it fail and what should the README say instead?")
    base = os.environ.get("NOSANA_URL", "")
    reason, by = ff.get("error_line", ""), "raw error line"
    if base:
        try:
            reason, by = ask(base, prompt), f"{MODEL} on Nosana"
        except Exception as e:  # keep the demo moving
            print("Nosana call failed, using raw error line:", e, file=sys.stderr)
    res["reason"], res["reason_by"] = reason, by
    json.dump(res, open(path, "w"), ensure_ascii=False, indent=2)
    print(json.dumps({"reason": reason, "reason_by": by}, ensure_ascii=False))


if __name__ == "__main__":
    main()
