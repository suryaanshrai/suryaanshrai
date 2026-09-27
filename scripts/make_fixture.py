"""Write scripts/fixture.json: a synthetic API response for offline previews (not real data)."""
import datetime as dt, json, random
from pathlib import Path

random.seed(7)
end = dt.date(2026, 9, 27)
start = end - dt.timedelta(days=end.isoweekday() % 7 + 52 * 7)
weeks, week, day = [], [], start
while day <= end:
    n = 0 if random.random() < 0.35 else random.choice([1, 1, 2, 3, 4, 6, 9, 14])
    lvl = ["NONE", "FIRST_QUARTILE", "SECOND_QUARTILE", "THIRD_QUARTILE", "FOURTH_QUARTILE"][
        0 if n == 0 else 1 if n < 3 else 2 if n < 5 else 3 if n < 9 else 4]
    week.append({"date": day.isoformat(), "contributionCount": n, "contributionLevel": lvl})
    if len(week) == 7:
        weeks.append({"contributionDays": week}); week = []
    day += dt.timedelta(days=1)
if week:
    weeks.append({"contributionDays": week})
total = sum(d["contributionCount"] for w in weeks for d in w["contributionDays"])

def repo(name, desc, lang, color, stars, pushed, langs):
    return {"name": name, "url": f"https://github.com/suryaanshrai/{name}", "description": desc,
            "stargazerCount": stars, "forkCount": 1, "pushedAt": pushed,
            "primaryLanguage": {"name": lang, "color": color},
            "languages": {"edges": [{"size": s, "node": {"name": n, "color": c}} for n, c, s in langs]}}

PY, JS, HT, CS = ("Python", "#3572A5"), ("JavaScript", "#f1e05a"), ("HTML", "#e34c26"), ("CSS", "#663399")
repos = [
    repo("sample-api", "A FastAPI service with async SQLAlchemy, auth and background jobs, deployed with Docker.", *PY, 12, "2026-09-25T10:00:00Z", [(*PY, 90000), (*HT, 4000)]),
    repo("sample-web", "Django web app sample for previews.", *PY, 5, "2026-08-02T10:00:00Z", [(*PY, 50000), (*JS, 20000), (*CS, 8000), (*HT, 9000)]),
    repo("sample-cli", None, *JS, 0, "2025-11-20T10:00:00Z", [(*JS, 30000)]),
    repo("a-very-long-repository-name-for-layout-testing", "Stress test: a deliberately long description that should wrap over several lines and eventually get truncated with an ellipsis at the end.", "C++", "#f34b7d", 128, "2024-01-01T10:00:00Z", [("C++", "#f34b7d", 20000), ("C", "#555555", 7000)]),
]
fixture = {"graphql": {"user": {
    "login": "suryaanshrai", "name": "Suryaansh Rai",
    "contributionsCollection": {"totalCommitContributions": 612, "totalPullRequestContributions": 48,
                                "totalIssueContributions": 17,
                                "contributionCalendar": {"totalContributions": total, "weeks": weeks}},
    "pinnedItems": {"nodes": [{k: v for k, v in r.items() if k != "languages"} for r in repos]},
    "repositories": {"totalCount": 31, "nodes": repos}}},
    "events": [
        {"type": "PushEvent", "repo": {"name": "suryaanshrai/sample-api"}, "payload": {}, "created_at": "2026-09-27T08:00:00Z"},
        {"type": "PushEvent", "repo": {"name": "suryaanshrai/sample-api"}, "payload": {}, "created_at": "2026-09-26T08:00:00Z"},
        {"type": "PullRequestEvent", "repo": {"name": "suryaanshrai/sample-api"}, "created_at": "2026-09-26T09:00:00Z",
         "payload": {"action": "opened", "number": 5, "pull_request": {"url": "https://api.github.com/repos/suryaanshrai/sample-api/pulls/5", "id": 1, "number": 5}}},
        {"type": "PullRequestEvent", "repo": {"name": "someorg/lib"}, "created_at": "2026-09-24T08:00:00Z",
         "payload": {"action": "closed", "pull_request": {"number": 42, "title": "Fix [edge] case in *parser*", "merged": True, "html_url": "https://github.com/someorg/lib/pull/42"}}},
        {"type": "WatchEvent", "repo": {"name": "astral-sh/uv"}, "payload": {"action": "started"}, "created_at": "2026-09-20T08:00:00Z"},
        {"type": "CreateEvent", "repo": {"name": "suryaanshrai/sample-cli"}, "payload": {"ref_type": "repository"}, "created_at": "2026-09-10T08:00:00Z"},
        {"type": "IssuesEvent", "repo": {"name": "someorg/lib"}, "created_at": "2026-08-01T08:00:00Z",
         "payload": {"action": "opened", "issue": {"number": 7, "title": "Docs typo", "html_url": "https://github.com/someorg/lib/issues/7"}}},
    ]}
Path(__file__).with_name("fixture.json").write_text(json.dumps(fixture, indent=1))
