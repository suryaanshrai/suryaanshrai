#!/usr/bin/env python3
"""Render the REPL-themed profile README: animated SVGs in assets/ + README blocks.

Usage:
  GITHUB_TOKEN=... python3 scripts/generate.py          # live data from the GitHub API
  python3 scripts/generate.py --fixture scripts/fixture.json   # offline preview

Standard library only, so the workflow needs nothing but Python.
"""
import argparse
import collections
import datetime as dt
import json
import os
import re
import sys
import textwrap
import urllib.request
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
README = ROOT / "README.md"
FACTS = Path(__file__).resolve().parent / "facts.txt"
LOGIN = os.environ.get("PROFILE_LOGIN", "suryaanshrai")

WIDTH = 840
PAD = 28
CW = 8.4          # monospace advance at 14px; every token gets textLength=len*CW
LH = 22
TITLE_BAR = 40

THEMES = {
    "dark": dict(bg="#0d1117", bar="#161b22", border="#30363d", fg="#e6edf3", mu="#8b949e",
                 pr="#ffd43b", kw="#ff7b72", st="#a5d6ff", nu="#79c0ff", fn="#d2a8ff",
                 cm="#8b949e", cur="#ffd43b",
                 lv=["#161b22", "#1e3a5f", "#2a5f9e", "#3d8bfd", "#ffd43b"]),
    "light": dict(bg="#ffffff", bar="#f6f8fa", border="#d0d7de", fg="#1f2328", mu="#656d76",
                  pr="#3572a5", kw="#cf222e", st="#0a3069", nu="#0550ae", fn="#8250df",
                  cm="#6e7781", cur="#3572a5",
                  lv=["#ebedf0", "#c6dcf5", "#7fb0e8", "#3572a5", "#f2b705"]),
}

# --------------------------------------------------------------------------- highlighting

TOKEN = re.compile(r"""
    (?P<cm>\#.*$)
  | (?P<st>'[^']*'|"[^"]*")
  | (?P<kw>\b(?:from|import|for|in|def|return|class|True|False|None|lambda)\b)
  | (?P<fn>\b[A-Za-z_]\w*(?=\())
  | (?P<nu>\b\d[\d_]*(?:[,.]\d+)*%?)
  | (?P<ws>\s+)
  | (?P<fg>[A-Za-z_]\w*|.)
""", re.VERBOSE)


def hl(code):
    """Split a line of Python-ish text into (text, css-class) tokens."""
    out = []
    for m in TOKEN.finditer(code):
        kind, text = m.lastgroup, m.group()
        if out and out[-1][1] == kind:
            out[-1] = (out[-1][0] + text, kind)
        else:
            out.append((text, kind))
    return out


# --------------------------------------------------------------------------- svg session

class Session:
    """A terminal window whose lines appear as a typed-out REPL session."""

    def __init__(self, title, theme, width=WIDTH, pad=PAD):
        self.t = THEMES[theme]
        self.title, self.w, self.pad = title, width, pad
        self.y = TITLE_BAR + 30   # baseline of the next line
        self.clock = 0.3          # seconds; when the next thing appears
        self.body, self.keyframes = [], []
        self.n = 0

    # -- primitives
    def text(self, x, y, s, cls="fg", extra=""):
        return (f'<text x="{x:.1f}" y="{y:.1f}" class="{cls}" '
                f'textLength="{len(s) * CW:.1f}"{extra}>{escape(s)}</text>')

    def tokens(self, x, y, toks):
        parts = []
        for s, kind in toks:
            if kind.startswith("#"):
                parts.append(self.text(x, y, s, "fg", f' style="fill:{kind}"'))
            elif kind != "ws":
                parts.append(self.text(x, y, s, kind))
            x += len(s) * CW
        return "".join(parts)

    def appear(self, inner, delay=None):
        delay = self.clock if delay is None else delay
        return f'<g class="o" style="animation-delay:{delay:.2f}s">{inner}</g>'

    # -- lines
    def input(self, code, prompt=">>> "):
        x0 = self.pad + len(prompt) * CW
        y, n = self.y, max(len(code), 1)
        dur = max(0.35, n * 0.035)
        self.n += 1
        cid = f"c{self.n}"
        width = n * CW
        clip = (f'<clipPath id="{cid}"><rect class="ty" x="{x0:.1f}" y="{y - 15}" '
                f'width="{width + CW:.1f}" height="{LH}" '
                f'style="animation:type {dur:.2f}s steps({n}) {self.clock:.2f}s both"/></clipPath>')
        self.keyframes.append(f"@keyframes m{self.n}{{to{{transform:translateX({width:.1f}px)}}}}")
        cursor = (f'<rect x="{x0:.1f}" y="{y - 13}" width="{CW:.1f}" height="16" class="cur" opacity="0" '
                  f'style="animation:m{self.n} {dur:.2f}s steps({n}) {self.clock:.2f}s both">'
                  f'<set attributeName="opacity" to="1" begin="{self.clock:.2f}s" dur="{dur:.2f}s"/></rect>')
        self.body.append(clip + self.appear(self.text(self.pad, y, prompt.rstrip(), "pr")))
        self.body.append(f'<g clip-path="url(#{cid})">{self.tokens(x0, y, hl(code))}</g>{cursor}')
        self.clock += dur + 0.25
        self.y += LH

    def output(self, line, toks=None, gap=0.07):
        toks = toks if toks is not None else hl(line)
        self.body.append(self.appear(self.tokens(self.pad, self.y, toks)))
        self.clock += gap
        self.y += LH

    def blank(self, h=LH // 2):
        self.y += h

    def block(self, height, fn):
        """fn(top_y, start_time) -> (svg, seconds it animates for)."""
        svg, dur = fn(self.y - 15, self.clock)
        self.body.append(svg)
        self.clock += dur
        self.y += height

    def idle(self):
        x0 = self.pad + 4 * CW
        cur = f'<rect x="{x0:.1f}" y="{self.y - 13}" width="{CW:.1f}" height="16" class="cur blink"/>'
        self.body.append(self.appear(self.text(self.pad, self.y, ">>>", "pr") + cur))
        self.y += LH

    # -- document
    def render(self):
        t = self.t
        h = int(self.y - LH + 26)
        w = self.w
        dots = "".join(f'<circle cx="{20 + i * 20}" cy="{TITLE_BAR / 2}" r="6" fill="{c}"/>'
                       for i, c in enumerate(("#ff5f57", "#febc2e", "#28c840")))
        style = f"""
text{{font-family:ui-monospace,SFMono-Regular,'SF Mono',Menlo,Consolas,'Liberation Mono',monospace;font-size:14px;white-space:pre}}
.fg{{fill:{t['fg']}}}.mu{{fill:{t['mu']}}}.pr{{fill:{t['pr']};font-weight:700}}.kw{{fill:{t['kw']}}}
.st{{fill:{t['st']}}}.nu{{fill:{t['nu']}}}.fn{{fill:{t['fn']}}}.cm{{fill:{t['cm']};font-style:italic}}
.ttl{{fill:{t['mu']};font-size:12px}}.sm{{font-size:11px}}.cur{{fill:{t['cur']}}}
.o{{animation:fade .3s ease-out both}}
.ty{{transform-box:fill-box;transform-origin:0 50%}}
.pop{{transform-box:fill-box;transform-origin:center;animation:pop .45s ease-out both}}
.grow{{transform-box:fill-box;transform-origin:0 50%;animation:grow .9s cubic-bezier(.2,.8,.2,1) both}}
.blink{{animation:blink 1.1s steps(1) infinite}}
@keyframes fade{{from{{opacity:0}}to{{opacity:1}}}}
@keyframes type{{from{{transform:scaleX(0)}}to{{transform:scaleX(1)}}}}
@keyframes pop{{from{{opacity:0;transform:scale(.2)}}to{{opacity:1;transform:scale(1)}}}}
@keyframes grow{{from{{transform:scaleX(0)}}to{{transform:scaleX(1)}}}}
@keyframes blink{{50%{{opacity:0}}}}
{''.join(self.keyframes)}
@media (prefers-reduced-motion:reduce){{*{{animation:none!important}}}}"""
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" '
            f'role="img" aria-label="{escape(self.title)}">'
            f'<title>{escape(self.title)}</title><style>{style}</style>'
            f'<rect x="0.5" y="0.5" width="{w - 1}" height="{h - 1}" rx="12" fill="{t["bg"]}" stroke="{t["border"]}"/>'
            f'<path d="M1 {TITLE_BAR}V12.5A12 12 0 0 1 12.5 1H{w - 12.5}A12 12 0 0 1 {w - 1} 12.5V{TITLE_BAR}Z" fill="{t["bar"]}"/>'
            f'<line x1="1" x2="{w - 1}" y1="{TITLE_BAR}" y2="{TITLE_BAR}" stroke="{t["border"]}"/>'
            f'{dots}<text x="{w / 2}" y="{TITLE_BAR / 2 + 4}" text-anchor="middle" class="ttl">{escape(self.title)}</text>'
            + "".join(self.body) + "</svg>\n"
        )


# --------------------------------------------------------------------------- data

QUERY = """
query($login: String!) {
  user(login: $login) {
    login name
    contributionsCollection {
      totalCommitContributions totalPullRequestContributions totalIssueContributions
      contributionCalendar { totalContributions weeks { contributionDays { date contributionCount contributionLevel } } }
    }
    pinnedItems(first: 4, types: REPOSITORY) { nodes { ... on Repository { ...Repo } } }
    repositories(first: 100, ownerAffiliations: OWNER, isFork: false, privacy: PUBLIC,
                 orderBy: {field: PUSHED_AT, direction: DESC}) {
      totalCount
      nodes { ...Repo languages(first: 8, orderBy: {field: SIZE, direction: DESC}) { edges { size node { name color } } } }
    }
  }
}
fragment Repo on Repository { name url description stargazerCount forkCount pushedAt primaryLanguage { name color } }
"""


def api(url, token, body=None):
    req = urllib.request.Request(url, data=json.dumps(body).encode() if body else None, headers={
        "Authorization": f"bearer {token}", "Accept": "application/vnd.github+json",
        "User-Agent": f"{LOGIN}-profile-generator"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def fetch_live():
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        sys.exit("GITHUB_TOKEN is not set (or pass --fixture for offline rendering)")
    gql = api("https://api.github.com/graphql", token, {"query": QUERY, "variables": {"login": LOGIN}})
    if gql.get("errors") or not (gql.get("data") or {}).get("user"):
        sys.exit(f"GraphQL error: {json.dumps(gql.get('errors'))}")
    events = api(f"https://api.github.com/users/{LOGIN}/events/public?per_page=50", token)
    return {"graphql": gql["data"], "events": events}


LEVELS = {"NONE": 0, "FIRST_QUARTILE": 1, "SECOND_QUARTILE": 2, "THIRD_QUARTILE": 3, "FOURTH_QUARTILE": 4}


def streaks(days):
    longest = run = 0
    for d in days:
        run = run + 1 if d["count"] else 0
        longest = max(longest, run)
    current = 0
    tail = days[:-1] if days and not days[-1]["count"] else days   # today may just be early
    for d in reversed(tail):
        if not d["count"]:
            break
        current += 1
    return current, longest


def normalize(raw):
    u = raw["graphql"]["user"]
    cc = u["contributionsCollection"]
    weeks = [[{"date": d["date"], "count": d["contributionCount"], "level": LEVELS.get(d["contributionLevel"], 0)}
              for d in w["contributionDays"]] for w in cc["contributionCalendar"]["weeks"]]
    days = [d for w in weeks for d in w]
    repos = u["repositories"]["nodes"]

    langs, colors = collections.Counter(), {}
    for r in repos:
        for e in r["languages"]["edges"]:
            langs[e["node"]["name"]] += e["size"]
            colors[e["node"]["name"]] = e["node"]["color"]
    total = sum(langs.values()) or 1

    pinned = [p for p in u["pinnedItems"]["nodes"] if p]
    if not pinned:
        pinned = sorted((r for r in repos if r["name"].lower() != LOGIN.lower()),
                        key=lambda r: (r["stargazerCount"], r["pushedAt"]), reverse=True)[:4]
    current, longest = streaks(days)
    return {
        "login": u["login"],
        "weeks": weeks,
        "total": cc["contributionCalendar"]["totalContributions"],
        "commits": cc["totalCommitContributions"],
        "prs": cc["totalPullRequestContributions"],
        "issues": cc["totalIssueContributions"],
        "repos": u["repositories"]["totalCount"],
        "stars": sum(r["stargazerCount"] for r in repos),
        "streak": (current, longest),
        "languages": [(n, s / total, colors.get(n) or "#8b949e") for n, s in langs.most_common(5)],
        "projects": pinned,
        "events": raw["events"],
    }


# --------------------------------------------------------------------------- views

def hero(theme):
    s = Session("suryaansh@github: ~ — python3", theme)
    s.output('Python 3.13.0 (main) [suryaansh edition] on github', [(
        'Python 3.13.0 (main) [suryaansh edition] on github', "mu")], gap=0)
    s.output('', [('Type "help", "about" or "contact" for more information.', "mu")], gap=0.2)
    s.blank()
    s.input("from suryaansh import me")
    s.input("me.name")
    s.output("'Suryaansh Rai'")
    s.input("me.role")
    s.output("'Software Engineer'  # a budding one, always shipping")
    s.input("me.loves")
    s.output("['solving problems', 'conversing about solutions']")
    s.input("me.motto")
    s.output("'Building software is just the manifestation of this passion.'")
    s.idle()
    return s.render()


def stack(theme):
    s = Session("me.stack", theme)
    s.input("me.stack")
    for line in ("{",
                 "    'languages':  ['Python', 'JavaScript', 'C', 'C++', 'SQL'],",
                 "    'frameworks': ['Django', 'Flask', 'FastAPI'],",
                 "    'tooling':    ['Git', 'GitHub', 'Docker', 'Linux', 'Bash', 'VS Code'],",
                 "}"):
        s.output(line)
    s.idle()
    return s.render()


def stats(d, theme):
    s = Session("me.stats()", theme)
    cur, best = d["streak"]
    s.input("me.stats()")
    rows = [("contributions", f"{d['total']:,}", "# last 12 months"),
            ("commits", f"{d['commits']:,}", ""),
            ("pull_requests", f"{d['prs']:,}", ""),
            ("issues", f"{d['issues']:,}", ""),
            ("public_repos", f"{d['repos']:,}", ""),
            ("stars_earned", f"{d['stars']:,}", "")]
    s.output("Stats(")
    for k, v, c in rows:
        s.output(f"    {k:<14}= {v},  {c}".rstrip())
    s.output(f"    {'streak':<14}= Streak(current={cur}, longest={best}),  # days")
    s.output(")")
    if d["languages"]:
        s.blank()
        s.input("me.languages(top=5)")
        t = s.t
        bar_x, bar_w = s.pad + 14 * CW, 440

        def bars(top, start):
            parts = []
            for i, (name, share, color) in enumerate(d["languages"]):
                y = top + i * LH
                delay = start + i * 0.12
                parts.append(s.appear(s.text(s.pad, y + 13, name[:13], "fg"), delay))
                parts.append(s.appear(f'<rect x="{bar_x:.1f}" y="{y + 4}" width="{bar_w}" height="10" rx="5" fill="{t["lv"][0]}"/>', delay))
                parts.append(f'<rect class="grow" style="animation-delay:{delay:.2f}s" x="{bar_x:.1f}" y="{y + 4}" '
                             f'width="{max(bar_w * share, 10):.1f}" height="10" rx="5" fill="{color}"/>')
                parts.append(s.appear(s.text(bar_x + bar_w + 14, y + 13, f"{share * 100:5.1f}%", "nu"), delay))
            return "".join(parts), len(d["languages"]) * 0.12 + 0.6

        s.block(len(d["languages"]) * LH, bars)
    s.idle()
    return s.render()


def contributions(d, theme):
    s = Session("me.contributions.plot()", theme)
    s.input("me.contributions.plot()")
    t, weeks = s.t, d["weeks"]
    cell, gap = 11, 3
    gx = s.pad + 30

    def grid(top, start):
        parts, prev_month = [], None
        top += 18
        for c, week in enumerate(weeks):
            month = week[0]["date"][:7]
            if month != prev_month and c < len(weeks) - 2:
                if prev_month is not None or week[0]["date"][8:] <= "07":
                    name = dt.date.fromisoformat(week[0]["date"]).strftime("%b")
                    parts.append(f'<text x="{gx + c * (cell + gap)}" y="{top - 6}" class="mu sm">{name}</text>')
                prev_month = month
            first_wd = (dt.date.fromisoformat(week[0]["date"]).weekday() + 1) % 7  # Sunday = 0
            for r, day in enumerate(week):
                row = first_wd + r if c == 0 else r
                parts.append(f'<rect class="pop" style="animation-delay:{start + c * 0.018:.2f}s" '
                             f'x="{gx + c * (cell + gap)}" y="{top + row * (cell + gap)}" width="{cell}" '
                             f'height="{cell}" rx="2.5" fill="{t["lv"][day["level"]]}">'
                             f'<title>{day["date"]}: {day["count"]}</title></rect>')
        for row, label in ((1, "Mon"), (3, "Wed"), (5, "Fri")):
            parts.append(f'<text x="{s.pad}" y="{top + row * (cell + gap) + 9}" class="mu sm">{label}</text>')
        return "".join(parts), len(weeks) * 0.018 + 0.4

    s.block(18 + 7 * (cell + gap) + 8, grid)

    days = [x for w in weeks for x in w]
    best = max(days, key=lambda x: x["count"], default=None)
    by_wd = collections.Counter()
    for x in days:
        by_wd[dt.date.fromisoformat(x["date"]).strftime("%a")] += x["count"]
    busiest = by_wd.most_common(1)[0][0] if by_wd and best and best["count"] else "-"
    best_txt = (f"{dt.date.fromisoformat(best['date']).strftime('%b %d')} ({best['count']})"
                if best and best["count"] else "-")
    s.output(f"# {d['total']:,} contributions · best day {best_txt} · busiest on {busiest}s")

    legend_x = WIDTH - s.pad - 5 * 14 - 2 * CW * 4 - 12

    def legend(top, start):
        parts = [s.text(legend_x, top + 12, "less", "mu")]
        for i, c in enumerate(t["lv"]):
            parts.append(f'<rect x="{legend_x + 4 * CW + 6 + i * 14}" y="{top + 2}" width="11" height="11" rx="2.5" fill="{c}"/>')
        parts.append(s.text(legend_x + 4 * CW + 12 + 5 * 14, top + 12, "more", "mu"))
        return s.appear("".join(parts), start), 0

    s.y -= LH
    s.block(LH, legend)
    s.idle()
    return s.render()


def ago(iso, now):
    days = (now - dt.datetime.fromisoformat(iso.replace("Z", "+00:00"))).days
    if days < 1:
        return "today"
    if days < 2:
        return "yesterday"
    if days < 14:
        return f"{days} days ago"
    if days < 60:
        return f"{days // 7} weeks ago"
    if days < 365:
        return f"{days // 30} months ago"
    return f"{days // 365}y ago"


def project_card(p, theme, now):
    name = p["name"] if len(p["name"]) <= 30 else p["name"][:29] + "…"
    s = Session(f"~/{name}", theme, width=410, pad=20)
    s.input(f"import {re.sub(r'[^A-Za-z0-9_…]', '_', name)}")
    s.input("help(_)")
    desc = textwrap.wrap(p.get("description") or "No description yet — read the code!", 42)[:3]
    if len(desc) == 3 and len(textwrap.wrap(p.get("description") or "", 42)) > 3:
        desc[2] = desc[2][:39] + "..."
    for line in desc + [""] * (3 - len(desc)):
        s.output(line, [(line, "st")])
    lang = p.get("primaryLanguage") or {}
    meta = [("●", lang.get("color") or s.t["mu"]), (" ", "ws"), (lang.get("name") or "text", "fg"),
            (f"   ★ {p['stargazerCount']}", "nu"), (f"   updated {ago(p['pushedAt'], now)}", "cm")]
    s.output("", meta)
    return s.render()


def md(s):
    return re.sub(r"([\[\]*_`<>|])", r"\\\1", s)


def recent(events, now, limit=6):
    lines, seen = [], set()
    for e in events:
        repo = e["repo"]["name"]
        rl = f"[{repo}](https://github.com/{repo})"
        p = e.get("payload") or {}
        t = e["type"]
        if t == "PushEvent":
            text = f"🔨 Pushed to {rl}"
        elif t == "PullRequestEvent" and p.get("pull_request"):
            pr = p["pull_request"]
            verb = "Merged" if p.get("action") == "closed" and pr.get("merged") else p.get("action", "").capitalize()
            text = f"🔀 {verb} PR [#{pr['number']} {md(pr.get('title') or '')}]({pr['html_url']}) in {rl}"
        elif t == "IssuesEvent" and p.get("issue"):
            iss = p["issue"]
            text = f"🐛 {p.get('action', '').capitalize()} issue [#{iss['number']} {md(iss.get('title') or '')}]({iss['html_url']}) in {rl}"
        elif t == "IssueCommentEvent" and p.get("issue"):
            iss = p["issue"]
            text = f"💬 Commented on [#{iss['number']}]({iss['html_url']}) in {rl}"
        elif t == "PullRequestReviewEvent":
            text = f"👀 Reviewed a PR in {rl}"
        elif t == "CreateEvent" and p.get("ref_type") == "repository":
            text = f"✨ Created {rl}"
        elif t == "ReleaseEvent":
            text = f"🚀 Released `{md((p.get('release') or {}).get('tag_name', ''))}` of {rl}"
        elif t == "WatchEvent":
            text = f"⭐ Starred {rl}"
        elif t == "ForkEvent":
            text = f"🍴 Forked {rl}"
        else:
            continue
        key = (t, repo) if t in ("PushEvent", "WatchEvent", "IssueCommentEvent", "PullRequestReviewEvent") else text
        if key in seen:
            continue
        seen.add(key)
        lines.append(f"- {text} <sub>· {ago(e['created_at'], now)}</sub>")
        if len(lines) == limit:
            break
    return "\n".join(lines) or "- _Quiet week — probably reading docs._"


def fun_fact(today):
    facts = [f.strip() for f in FACTS.read_text().splitlines() if f.strip() and not f.startswith("#")]
    return facts[today.timetuple().tm_yday % len(facts)]


# --------------------------------------------------------------------------- output

def picture(name, alt, width=None, attrs=""):
    w = f' width="{width}"' if width else ""
    return (f'<picture><source media="(prefers-color-scheme: dark)" srcset="assets/{name}-dark.svg">'
            f'<img src="assets/{name}-light.svg" alt="{escape(alt)}"{w}{attrs}></picture>')


def replace_block(text, name, content):
    pattern = re.compile(rf"(<!-- {name}:START -->)(.*?)(<!-- {name}:END -->)", re.S)
    if not pattern.search(text):
        sys.exit(f"README is missing the {name} markers")
    return pattern.sub(lambda m: f"{m.group(1)}\n{content}\n{m.group(3)}", text)


def write(name, svg):
    path = ASSETS / f"{name}.svg"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(svg)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fixture", help="render from a saved API response instead of the live API")
    ap.add_argument("--now", help="pretend it is this ISO datetime (for reproducible previews)")
    args = ap.parse_args()

    raw = json.loads(Path(args.fixture).read_text()) if args.fixture else fetch_live()
    now = dt.datetime.fromisoformat(args.now) if args.now else dt.datetime.now(dt.timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=dt.timezone.utc)
    d = normalize(raw)

    projects_dir = ASSETS / "projects"
    if projects_dir.exists():
        for old in projects_dir.glob("*.svg"):
            old.unlink()
    for theme in THEMES:
        write(f"hero-{theme}", hero(theme))
        write(f"stack-{theme}", stack(theme))
        write(f"stats-{theme}", stats(d, theme))
        write(f"contributions-{theme}", contributions(d, theme))
        for p in d["projects"]:
            write(f"projects/{p['name']}-{theme}", project_card(p, theme, now))

    cards = "\n".join(f'<a href="{p["url"]}">{picture("projects/" + p["name"], p["name"], "48%")}</a>'
                      for p in d["projects"])
    readme = README.read_text()
    readme = replace_block(readme, "PROJECTS",
                           f'<p align="center">\n{cards}\n</p>' if cards else "<p align=\"center\"><em>Nothing pinned yet.</em></p>")
    readme = replace_block(readme, "NOW", recent(d["events"], now))
    readme = replace_block(readme, "FACT", f"<em>{escape(fun_fact(now.date()))}</em>")
    README.write_text(readme)
    print(f"rendered {4 + len(d['projects'])} views x {len(THEMES)} themes; README updated")


if __name__ == "__main__":
    main()
