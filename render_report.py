#!/usr/bin/env python3
"""Render a README Check result.json into one self-contained report.html (1920x1080 projector view).

Usage:
  python3 render_report.py <result.json> [-o report.html]

Standard library only. The page loads nothing from the network: images and links in the README
are shown as text, and the only href is the checked repo URL.
"""
import argparse, datetime, html, json, os, re, sys

FENCE = re.compile(r"^(\s*)(```|~~~)\s*([\w+-]*)")  # same as readme_check.extract_steps
TAIL_AFTER_LAST_STEP = 40
NO_STEP_LINES = 60

BADGE = {
    "pass": ("&#10003;", "pass", "passed"),
    "fail": ("&#10007;", "fail", "failed"),
    "skip": ("SKIP", "skip", "not run"),
    "timeout": ("TIMEOUT", "amber", "timed out"),
    "box_limit": ("BOX LIMIT", "amber", "sandbox limit"),
}

E = html.escape


# ---------- inline markdown ----------
def inline(text):
    t = text
    t = re.sub(r"\[!\[[^\]]*\]\([^)]*\)\]\([^)]*\)", "", t)      # [![badge](img)](link)
    t = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", t)                   # ![img](src)
    t = re.sub(r"<!--.*?-->", "", t)
    t = re.sub(r"</?[A-Za-z][^>]*>", "", t)                      # inline html tags
    t = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", t)               # [text](url) -> text
    t = re.sub(r"\[([^\]]+)\]\[[^\]]*\]", r"\1", t)              # [text][ref] -> text
    if not t.strip():
        return ""
    parts = re.split(r"(`[^`]+`)", t)
    out = []
    for p in parts:
        if len(p) > 1 and p.startswith("`") and p.endswith("`"):
            out.append("<code>" + E(p[1:-1]) + "</code>")
        else:
            s = E(p)
            s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
            s = re.sub(r"__(.+?)__", r"<strong>\1</strong>", s)
            out.append(s)
    return "".join(out).strip()


# ---------- block markdown, keeping README line numbers ----------
def render_readme(readme, step_by_line, fail_line, focus_line):
    lines = readme.splitlines()
    n = len(lines)
    step_lines = sorted(step_by_line)
    limit = min(n, (step_lines[-1] + TAIL_AFTER_LAST_STEP) if step_lines else NO_STEP_LINES)
    out, para = [], []
    title_done = [False]
    in_comment = False

    def flush():
        if para:
            txt = " ".join(para)
            h = inline(txt)
            if h:
                out.append(f"<p>{h}</p>")
            para.clear()

    i = 0
    while i < limit:
        raw = lines[i]
        s = raw.strip()
        if in_comment:
            if "-->" in s:
                in_comment = False
            i += 1
            continue
        if s.startswith("<!--") and "-->" not in s:
            flush(); in_comment = True; i += 1
            continue
        m = FENCE.match(raw)
        if m:
            flush()
            indent, fence = m.group(1), m.group(2)
            i += 1
            rows = []
            while i < n and not re.match(r"^\s*" + re.escape(fence), lines[i]):
                if i >= limit and not any(l > i for l in step_lines):
                    break
                ln = i + 1
                body = lines[i][len(indent):] if lines[i].startswith(indent) else lines[i].strip()
                rows.append(code_row(ln, body, step_by_line.get(ln), ln == fail_line, ln == focus_line))
                i += 1
            i += 1
            out.append('<div class="code">' + "".join(rows) + "</div>")
            continue
        if not s:
            flush(); i += 1
            continue
        hm = re.match(r"^(#{1,6})\s+(.*?)\s*#*\s*$", s)
        if hm:
            flush()
            level = len(hm.group(1))
            h = inline(hm.group(2))
            if h:
                if level == 1 and not title_done[0]:
                    out.append(f'<h1 class="title">{h}</h1>')
                    title_done[0] = True
                else:
                    tag = {1: "h2", 2: "h2", 3: "h3"}.get(level, "h4")
                    out.append(f"<{tag}>{h}</{tag}>")
            i += 1
            continue
        if re.match(r"^</?[A-Za-z][^>]*>\s*$", s) or re.match(r"^<(img|p|div|a|br|picture|source|h\d)\b", s, re.I):
            # raw HTML block line: keep only its readable text, never its src/href
            flush()
            h = inline(s)
            if h:
                out.append(f"<p>{h}</p>")
            i += 1
            continue
        lm = re.match(r"^(\s*)([-*+]|\d+[.)])\s+(.*)$", raw)
        if lm:
            flush()
            mark = "&bull;" if lm.group(2) in "-*+" else E(lm.group(2))
            h = inline(lm.group(3))
            if h:
                out.append(f'<p class="li"><span class="mk">{mark}</span>{h}</p>')
            i += 1
            continue
        if re.match(r"^\|?\s*:?-{3,}", s):  # table separator row
            i += 1
            continue
        if s.startswith(">"):
            flush()
            h = inline(s.lstrip("> "))
            if h:
                out.append(f'<p class="quote">{h}</p>')
            i += 1
            continue
        if re.match(r"^(-{3,}|\*{3,}|_{3,}|={3,})$", s):
            flush(); i += 1
            continue
        para.append(s.strip("|").replace("|", " · ") if s.startswith("|") else s)
        i += 1
    flush()
    rest = n - limit
    if rest > 0:
        out.append(f'<p class="more">&hellip; README continues ({rest} more lines not shown)</p>')
    return "\n".join(out)


def code_row(ln, body, step, is_fail, is_focus):
    rid = ' id="focus"' if is_focus else ""
    if not step:
        return f'<div class="row"{rid} data-line="{ln}"><span class="gut"></span><span class="txt">{E(body) or "&nbsp;"}</span></div>'
    st = step.get("status", "")
    label, cls, word = BADGE.get(st, (E(st.upper() or "?"), "skip", st))
    extra = ""
    note = step.get("note", "")
    if st in ("timeout", "box_limit") and note:
        extra = f'<span class="note">{E(note)}</span>'
    elif st == "skip":
        extra = '<span class="note">not run</span>'
    rowcls = f"row step s-{cls}" + (" failrow" if is_fail else "")
    return (f'<div class="{rowcls}"{rid} data-line="{ln}" title="line {ln}: {E(word)}">'
            f'<span class="gut"><span class="badge b-{cls}">{label}</span></span>'
            f'<span class="txt">{E(body)}{extra}</span></div>')


# ---------- page ----------
def age_text(date_s, ref_s):
    try:
        d = datetime.date.fromisoformat(date_s[:10])
        r = datetime.date.fromisoformat((ref_s or "")[:10]) if ref_s else datetime.date.today()
    except ValueError:
        return ""
    days = (r - d).days
    if days >= 365:
        return f" ({days / 365.25:.1f} years ago)"
    if days >= 60:
        return f" ({days // 30} months ago)"
    return ""


def build(res):
    steps = res.get("steps") or []
    status = res.get("status") or ""
    url = res.get("url") or ""
    readme = res.get("readme") or ""
    step_by_line = {}
    for s in steps:
        if isinstance(s.get("line"), int):
            step_by_line.setdefault(s["line"], s)
    fail_idx = next((k for k, s in enumerate(steps) if s.get("status") == "fail"), None)
    fail = steps[fail_idx] if fail_idx is not None else None
    ff = res.get("first_failure") or {}
    n_total = len(steps)
    n_pass = sum(1 for s in steps if s.get("status") == "pass")
    n_amber = sum(1 for s in steps if s.get("status") in ("timeout", "box_limit"))
    fail_line = fail.get("line") if fail else None
    focus_line = fail_line or (steps[0].get("line") if steps else None)

    # status pill + right panel
    if status == "clone_failed":
        pill = ("fail", "Clone failed")
        panel = (f'<div class="callout c-fail"><div class="ch">CLONE FAILED</div>'
                 f'<div class="lbl">Command</div><pre class="mono">git clone {E(url)}</pre>'
                 f'<div class="lbl">Error</div><pre class="mono">{E(res.get("error_line", ""))}</pre>'
                 f'<div class="kv">Exit code: <b>{E(str((res.get("clone") or {}).get("exit_code", "?")))}</b></div></div>')
    elif fail:
        pill = ("fail", f"Run stopped at step {fail_idx + 1} of {n_total}")
        cmd = fail.get("cmd") or ff.get("cmd", "")
        err = fail.get("error_line") or ff.get("error_line", "")
        reason = res.get("reason") or ff.get("reason") or fail.get("reason")
        code = fail.get("exit_code", ff.get("exit_code", "?"))
        if isinstance(reason, str) and reason.strip() and reason.strip() != err.strip():
            why = (f'<div class="reason">{E(reason.strip())}</div>'
                   f'<div class="lbl">Error line</div><pre class="mono err">{E(err)}</pre>')
        else:
            why = f'<div class="lbl">Error line</div><pre class="mono err">{E(err)}</pre>'
        panel = (f'<div class="callout c-fail" id="callout"><span class="ptr"></span>'
                 f'<div class="ch">FAILED HERE</div>'
                 f'<div class="lbl">Step {fail_idx + 1} &middot; README line {E(str(fail_line))}</div>'
                 f'<pre class="mono cmd">{E(cmd)}</pre>{why}'
                 f'<div class="kv">Exit code: <b>{E(str(code))}</b></div>'
                 f'<div class="sub">{n_total - fail_idx - 1} later step(s) not run</div></div>')
    elif n_total == 0:
        pill = ("skip", "No install steps found")
        panel = ('<div class="callout c-skip"><div class="ch">NO STEPS</div>'
                 '<div class="reason">No install commands were found in the README code blocks.</div></div>')
    elif n_amber:
        pill = ("amber", f"{n_pass} of {n_total} passed")
        items = "".join(
            f'<div class="kv"><span class="badge b-amber">{BADGE[s["status"]][0]}</span> '
            f'<code>{E(s.get("cmd", ""))}</code><div class="sub">{E(s.get("note", ""))}</div></div>'
            for s in steps if s.get("status") in ("timeout", "box_limit"))
        panel = (f'<div class="callout c-amber"><div class="ch">NOT FULLY VERIFIED</div>'
                 f'<div class="reason">{n_pass} of {n_total} install steps passed in a fresh sandbox; '
                 f'{n_amber} could not be verified.</div>{items}</div>')
    else:
        pill = ("pass", "All passed")
        panel = (f'<div class="callout c-pass"><div class="ch">ALL PASSED</div>'
                 f'<div class="reason">All {n_total} install step{"s" if n_total != 1 else ""} '
                 f'passed in a fresh sandbox.</div>'
                 + "".join(f'<pre class="mono ok">&#10003; {E(s.get("cmd", ""))}</pre>' for s in steps)
                 + "</div>")

    sd = res.get("sandbox_deleted")
    sandbox = ('Sandbox deleted <span class="okc">&#10003;</span>' if sd is True
               else "Sandbox NOT deleted" if sd is False else "Sandbox kept")
    meta = []
    if res.get("box_python"):
        meta.append(E(res["box_python"]))
    if res.get("last_commit"):
        meta.append("Last commit " + E(res["last_commit"]) + E(age_text(res["last_commit"], res.get("finished"))))
    if res.get("extracted") is not None:
        k = res.get("extracted")
        meta.append(f"{E(str(k))} step{'s' if k != 1 else ''} extracted")
    meta.append(sandbox)
    url_html = (f'<a class="url" href="{E(url, quote=True)}">{E(url)}</a>'
                if re.match(r"^https?://[^\s\"'<>]+$", url) else f'<span class="url">{E(url)}</span>')

    body = render_readme(readme, step_by_line, fail_line, focus_line) if readme else \
        '<p class="more">README was not read.</p>'
    title = "README CHECK — " + (url.rstrip("/").split("/")[-1] if url else "report")

    return PAGE.format(
        title=E(title), url=url_html, pill_cls=pill[0], pill=E(pill[1]),
        meta="".join(f"<span>{m}</span>" for m in meta), readme=body, panel=panel)


PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
:root {{
  --ink:#111; --paper:#fff; --line:#222; --muted:#6b6b6b; --codebg:#ececec; --failbg:#c4c4c4;
  --green:#137a2c; --red:#c8102e; --amber:#b86e00; --gray:#8a8a8a;
  --sans: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial,
          "Hiragino Sans", "PingFang SC", "Noto Sans CJK JP", "Noto Sans CJK SC", sans-serif;
  --mono: ui-monospace, SFMono-Regular, Menlo, Consolas, "Liberation Mono", "DejaVu Sans Mono", monospace;
  --f-title: min(96px, 5vw); --f-h2: min(72px, 3.75vw); --f-h3: min(56px, 2.92vw);
  --f-body: min(40px, 2.08vw); --f-code: min(36px, 1.875vw); --f-band: min(32px, 1.67vw);
  --gap: min(40px, 2.1vw); --gut: min(190px, 9.9vw);
}}
* {{ box-sizing: border-box; }}
html, body {{ margin:0; background:var(--paper); color:var(--ink); font-family:var(--sans); }}
.band {{ position:sticky; top:0; z-index:10; background:var(--paper); border-bottom:4px solid var(--line);
  padding: 14px 32px; font-size:var(--f-band); }}
.band .r1, .band .r2 {{ display:flex; flex-wrap:wrap; align-items:center; gap: 10px 28px; }}
.band .r2 {{ margin-top:8px; font-weight:600; color:#333; }}
.band .r2 span + span::before {{ content:"|"; color:#999; margin-right:28px; }}
.brand {{ font-weight:900; letter-spacing:.02em; background:var(--ink); color:var(--paper); padding:4px 18px; }}
.url {{ font-family:var(--mono); font-weight:700; color:var(--ink); text-decoration:none;
  border:3px solid var(--line); padding:2px 14px; border-radius:6px; overflow-wrap:anywhere; }}
.pill {{ font-weight:800; color:#fff; padding:4px 18px; border-radius:6px; }}
.pill.fail {{ background:var(--red); }} .pill.pass {{ background:var(--green); }}
.pill.amber {{ background:var(--amber); }} .pill.skip {{ background:var(--gray); }}
.okc {{ color:var(--green); }}
.wrap {{ display:grid; grid-template-columns: 65fr 33fr; gap: var(--gap); padding: 24px 32px 50vh 32px; }}
.doc {{ border:3px solid var(--line); padding: 16px 32px 32px 32px; min-width:0; font-size:var(--f-body); line-height:1.35; }}
.doc .title {{ font-size:var(--f-title); line-height:1.05; margin:8px 0 12px; font-weight:900; }}
.doc h2 {{ font-size:var(--f-h2); line-height:1.1; margin:28px 0 12px; font-weight:900; }}
.doc h3 {{ font-size:var(--f-h3); line-height:1.15; margin:24px 0 10px; font-weight:800; }}
.doc h4 {{ font-size:var(--f-body); margin:20px 0 8px; font-weight:800; }}
.doc p {{ margin: 0 0 18px; overflow-wrap:anywhere; }}
.doc p.li {{ padding-left:1.2em; text-indent:-1.2em; margin-bottom:10px; font-weight:600; }}
.doc p.li .mk {{ display:inline-block; width:1.2em; text-indent:0; }}
.doc p.quote {{ border-left:6px solid #999; padding-left:16px; color:#333; }}
.doc p.more {{ color:var(--muted); font-style:italic; margin-top:24px; }}
.doc code {{ font-family:var(--mono); font-size:.9em; background:var(--codebg); padding:0 .2em; }}
.code {{ margin: 0 0 24px; font-family:var(--mono); font-size:var(--f-code); line-height:1.3; }}
.row {{ display:grid; grid-template-columns: var(--gut) 1fr; background:var(--codebg); border-bottom:2px solid var(--paper); }}
.row .gut {{ display:flex; align-items:center; justify-content:center; background:#dcdcdc; padding:6px 4px; }}
.row .txt {{ padding: 8px 20px; white-space:pre-wrap; overflow-wrap:anywhere; min-width:0; }}
.row.s-skip .txt {{ color:var(--muted); }}
.row.failrow {{ background:var(--failbg); outline:5px solid var(--red); outline-offset:-5px; position:relative; z-index:2; }}
.row.failrow .txt {{ font-weight:800; }}
.note {{ display:block; font-family:var(--sans); font-size:.72em; font-weight:700; color:var(--muted); margin-top:2px; }}
.badge {{ font-family:var(--sans); font-weight:900; font-size:min(30px, 1.6vw); padding:4px 12px; border-radius:6px;
  color:#fff; white-space:nowrap; line-height:1.2; }}
.b-pass {{ background:var(--green); font-size:min(40px, 2.1vw); }}
.b-fail {{ background:var(--red); font-size:min(40px, 2.1vw); }}
.b-skip {{ background:var(--gray); }}
.b-amber {{ background:var(--amber); }}
.side {{ position:relative; min-width:0; }}
.callout {{ background:var(--paper); border:6px solid var(--line); border-radius:22px; padding: 22px 28px;
  font-size:var(--f-code); line-height:1.3; position:sticky; top:200px; }}
.callout.c-fail {{ border-color:var(--red); }}
.callout.c-pass {{ border-color:var(--green); }}
.callout.c-amber {{ border-color:var(--amber); }}
.callout.c-skip {{ border-color:var(--gray); }}
.callout.placed {{ position:absolute; left:0; right:0; }}
.callout .ch {{ font-size:min(64px, 3.3vw); font-weight:900; line-height:1.05; margin-bottom:14px; }}
.c-fail .ch {{ color:var(--red); }} .c-pass .ch {{ color:var(--green); }} .c-amber .ch {{ color:var(--amber); }}
.callout .lbl {{ font-weight:800; color:var(--muted); font-size:.8em; margin-top:12px; }}
.callout .reason {{ font-weight:800; margin:8px 0; }}
.callout .kv {{ font-weight:800; margin-top:14px; }}
.callout .sub {{ color:var(--muted); font-size:.75em; font-weight:700; margin-top:10px; }}
.callout code {{ font-family:var(--mono); }}
.mono {{ font-family:var(--mono); font-size:1em; margin:6px 0 0; white-space:pre-wrap; overflow-wrap:anywhere;
  background:var(--codebg); padding:8px 12px; border-radius:6px; }}
.mono.err {{ background:#111; color:#fff; }}
.mono.ok {{ background:transparent; padding:2px 0; color:var(--green); font-weight:700; }}
.ptr {{ display:none; position:absolute; left:calc(-1 * var(--gap) - 48px); width:0; height:0;
  border-top:26px solid transparent; border-bottom:26px solid transparent;
  border-right: calc(var(--gap) + 48px) solid var(--red); top:40px; }}
.placed .ptr {{ display:block; }}
</style></head>
<body>
<header class="band">
  <div class="r1"><span class="brand">README CHECK</span>{url}<span class="pill {pill_cls}">{pill}</span></div>
  <div class="r2">{meta}</div>
</header>
<main class="wrap">
  <article class="doc">
{readme}
  </article>
  <aside class="side" id="side">{panel}</aside>
</main>
<script>
(function () {{
  function place() {{
    var row = document.getElementById("focus");
    if (!row) return;
    var side = document.getElementById("side");
    var co = document.getElementById("callout");
    var band = document.querySelector(".band").offsetHeight;
    var rowTop = row.getBoundingClientRect().top + window.scrollY;
    var rowMid = rowTop + row.offsetHeight / 2;
    if (co) {{
      var sideTop = side.getBoundingClientRect().top + window.scrollY;
      var ptrY = 70;
      co.classList.add("placed");
      co.style.top = Math.max(0, rowMid - sideTop - ptrY) + "px";
      var ptr = co.querySelector(".ptr");
      var coTop = sideTop + Math.max(0, rowMid - sideTop - ptrY);
      if (ptr) ptr.style.top = (rowMid - coTop - 26 - 6) + "px";
    }}
    var view = window.innerHeight - band;
    var target = rowTop - band - view * 0.35;
    if (co) {{
      var coBottom = co.getBoundingClientRect().top + window.scrollY + co.offsetHeight;
      if (coBottom - target > window.innerHeight - 24) target = coBottom - window.innerHeight + 24;
      if (target > rowTop - band - 24) target = rowTop - band - 24;
    }}
    window.scrollTo(0, Math.max(0, target));
  }}
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", place); else place();
  window.addEventListener("load", place);
  window.addEventListener("resize", place);
}})();
</script>
</body></html>
"""


def main():
    ap = argparse.ArgumentParser(description="Render README Check result.json to a self-contained HTML report.")
    ap.add_argument("result")
    ap.add_argument("-o", "--out")
    a = ap.parse_args()
    with open(a.result, encoding="utf-8") as f:
        res = json.load(f)
    out = a.out or os.path.join(os.path.dirname(os.path.abspath(a.result)), "report.html")
    page = build(res)
    with open(out, "w", encoding="utf-8") as f:
        f.write(page)
    print(out)


if __name__ == "__main__":
    main()
