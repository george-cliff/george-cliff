"""Generate the GitHub stats badge stack for the profile README.

Reads stats from GitHub's GraphQL API with GH_TOKEN, so private repositories
and contributions count too. Each row is rendered by shields.io, so the stack
matches the link badges, and the rows are combined into one SVG.

Usage:
    GH_TOKEN=... python github_stats.py output/github-stats.svg
    python github_stats.py preview.svg --sample   # made-up numbers, no token
"""
import datetime as dt
import json
import os
import re
import sys
import urllib.parse
import urllib.request

API = "https://api.github.com/graphql"
NOW = dt.datetime.now(dt.timezone.utc)
YEAR_START = NOW.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)

# Which stats to show, in order. Swap in any key from STATS below.
# The "_this_year" stats count from 1 January, to match the title.
SHOW = ["contributions_this_year", "active_days_this_year", "commits_this_year"]

# Badge look: match the style of the link badges in README.md.
STYLE = "for-the-badge"
TITLE = f"GitHub stats {NOW.year}"
TITLE_COLOUR = "181717"
LABEL_COLOUR = "181717"
VALUE_COLOUR = "164F4A"  # teal-800
GAP = 4  # pixels between rows



def graphql(query, variables=None):
    req = urllib.request.Request(
        API,
        data=json.dumps({"query": query, "variables": variables or {}}).encode(),
        headers={"Authorization": f"bearer {os.environ['GH_TOKEN']}", "Content-Type": "application/json"},
    )
    data = json.load(urllib.request.urlopen(req))
    if "errors" in data:
        raise RuntimeError(data["errors"])
    return data["data"]


def iso(d):
    return d.strftime("%Y-%m-%dT%H:%M:%SZ")


def commits_between(start, end):
    c = graphql(
        """query($from: DateTime!, $to: DateTime!) { viewer { contributionsCollection(from: $from, to: $to) {
             totalCommitContributions restrictedContributionsCount } } }""",
        {"from": iso(start), "to": iso(end)},
    )["viewer"]["contributionsCollection"]
    return c["totalCommitContributions"] + c["restrictedContributionsCount"]


def calendar(start=None, end=None):
    """The contribution calendar for a range, or the last year if no range is given."""
    if start:
        args, variables = "(from: $from, to: $to)", {"from": iso(start), "to": iso(end)}
        head = "query($from: DateTime!, $to: DateTime!)"
    else:
        args, variables, head = "", {}, "query"
    return graphql(
        head + " { viewer { contributionsCollection" + args + """ { contributionCalendar {
             totalContributions weeks { contributionDays { date contributionCount } } } } } }""",
        variables,
    )["viewer"]["contributionsCollection"]["contributionCalendar"]


def calendar_days(start=None, end=None):
    return [d for w in calendar(start, end)["weeks"] for d in w["contributionDays"]]


def streaks():
    days = calendar_days()
    longest = run = 0
    for d in days:
        run = run + 1 if d["contributionCount"] else 0
        longest = max(longest, run)
    # The current streak survives a quiet today: count back from yesterday if needed
    current = 0
    for d in reversed(days[:-1] if days and not days[-1]["contributionCount"] else days):
        if not d["contributionCount"]:
            break
        current += 1
    return current, longest


def plural(n, word):
    return f"{n:,} {word}{'' if n == 1 else 's'}"


def contributions_last_year():
    n = graphql("{ viewer { contributionsCollection { contributionCalendar { totalContributions } } } }")
    return "Contributions (last year)", f"{n['viewer']['contributionsCollection']['contributionCalendar']['totalContributions']:,}"


def contributions_this_year():
    return "Contributions", f"{calendar(YEAR_START, NOW)['totalContributions']:,}"


def commits_this_year():
    return "Commits", f"{commits_between(YEAR_START, NOW):,}"


def commits_this_month():
    return f"Commits in {NOW:%B}", f"{commits_between(NOW.replace(day=1, hour=0, minute=0, second=0), NOW):,}"


def commits_all_time():
    created = dt.datetime.fromisoformat(graphql("{ viewer { createdAt } }")["viewer"]["createdAt"].replace("Z", "+00:00"))
    total, start = 0, created
    while start < NOW:  # the API allows at most a year per query
        end = min(start.replace(year=start.year + 1), NOW)
        total += commits_between(start, end)
        start = end
    return "Commits (all time)", f"{total:,}"


def repositories():
    n = graphql("{ viewer { repositories(ownerAffiliations: OWNER) { totalCount } } }")["viewer"]["repositories"]["totalCount"]
    return "Repositories", f"{n:,}"


def public_repositories():
    n = graphql("{ viewer { repositories(ownerAffiliations: OWNER, privacy: PUBLIC) { totalCount } } }")
    return "Public repositories", f"{n['viewer']['repositories']['totalCount']:,}"


def stars_earned():
    total, cursor = 0, None
    while True:
        page = graphql(
            """query($after: String) { viewer { repositories(ownerAffiliations: OWNER, first: 100, after: $after) {
                 nodes { stargazerCount } pageInfo { hasNextPage endCursor } } } }""",
            {"after": cursor},
        )["viewer"]["repositories"]
        total += sum(r["stargazerCount"] for r in page["nodes"])
        if not page["pageInfo"]["hasNextPage"]:
            return "Stars earned", f"{total:,}"
        cursor = page["pageInfo"]["endCursor"]


def pull_requests():
    n = graphql("{ viewer { pullRequests { totalCount } } }")["viewer"]["pullRequests"]["totalCount"]
    return "Pull requests", f"{n:,}"


def issues():
    n = graphql("{ viewer { issues { totalCount } } }")["viewer"]["issues"]["totalCount"]
    return "Issues opened", f"{n:,}"


def followers():
    n = graphql("{ viewer { followers { totalCount } } }")["viewer"]["followers"]["totalCount"]
    return "Followers", f"{n:,}"


def years_on_github():
    created = dt.datetime.fromisoformat(graphql("{ viewer { createdAt } }")["viewer"]["createdAt"].replace("Z", "+00:00"))
    years = (NOW - created).days // 365
    return "On GitHub since", f"{created.year} ({plural(years, 'year')})"


def current_streak():
    return "Current streak", plural(streaks()[0], "day")


def longest_streak():
    return "Longest streak (last year)", plural(streaks()[1], "day")


def active_days_this_year():
    n = sum(1 for d in calendar_days(YEAR_START, NOW) if d["contributionCount"])
    return "Active days", f"{n:,}"


def active_days():
    n = sum(1 for d in calendar_days() if d["contributionCount"])
    return "Active days (last year)", f"{n:,}"


def top_language():
    sizes, cursor = {}, None
    while True:
        page = graphql(
            """query($after: String) { viewer { repositories(ownerAffiliations: OWNER, isFork: false, first: 100, after: $after) {
                 nodes { languages(first: 10) { edges { size node { name } } } } pageInfo { hasNextPage endCursor } } } }""",
            {"after": cursor},
        )["viewer"]["repositories"]
        for repo in page["nodes"]:
            for e in repo["languages"]["edges"]:
                sizes[e["node"]["name"]] = sizes.get(e["node"]["name"], 0) + e["size"]
        if not page["pageInfo"]["hasNextPage"]:
            break
        cursor = page["pageInfo"]["endCursor"]
    return "Top language", max(sizes, key=sizes.get) if sizes else "None yet"


STATS = {f.__name__: f for f in [
    contributions_this_year, active_days_this_year, contributions_last_year, commits_this_year, commits_this_month, commits_all_time, repositories,
    public_repositories, stars_earned, pull_requests, issues, followers, years_on_github,
    current_streak, longest_streak, active_days, top_language,
]}

SAMPLE = {
    "contributions_this_year": ("Contributions", "356"),
    "active_days_this_year": ("Active days", "121"),
    "contributions_last_year": ("Contributions (last year)", "412"),
    "commits_this_year": ("Commits", "318"),
    "commits_this_month": (f"Commits in {NOW:%B}", "47"),
    "repositories": ("Repositories", "11"),
    "active_days": ("Active days (last year)", "143"),
}


def shield(label, message, colour, label_colour=None, logo=None):
    esc = lambda t: urllib.parse.quote(t.replace("-", "--").replace("_", "__"), safe="")
    path = f"{esc(label)}-{esc(message)}-{colour}" if message else f"{esc(label)}-{colour}"
    params = {"style": STYLE}
    if label_colour:
        params["labelColor"] = label_colour
    if logo:
        params["logo"] = logo
    url = f"https://img.shields.io/badge/{path}?{urllib.parse.urlencode(params)}"
    return urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "github-stats"})).read().decode()


def stack(svgs, description):
    """Combine badge SVGs into one, one per row, giving each row's ids a unique prefix."""
    rows, y, width = [], 0, 0
    for i, svg in enumerate(svgs):
        w = float(re.search(r'<svg[^>]*\bwidth="([\d.]+)"', svg).group(1))
        h = float(re.search(r'<svg[^>]*\bheight="([\d.]+)"', svg).group(1))
        svg = re.sub(r'\bid="([^"]+)"', rf'id="r{i}-\1"', svg)
        svg = re.sub(r'url\(#([^)]+)\)', rf'url(#r{i}-\1)', svg)
        svg = re.sub(r'(xlink:)?href="#([^"]+)"', rf'\1href="#r{i}-\2"', svg)
        svg = re.sub(r"<svg\b", f'<svg x="0" y="{y:g}"', svg, count=1)
        rows.append(svg)
        y += h + GAP
        width = max(width, w)
    height = y - GAP
    return (f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
            f'width="{width:g}" height="{height:g}" role="img" aria-label="{description}">'
            f"<title>{description}</title>{''.join(rows)}</svg>\n")


def main():
    out, sample = sys.argv[1], "--sample" in sys.argv
    values = [SAMPLE[k] if sample else STATS[k]() for k in SHOW]
    svgs = [shield(TITLE, "", TITLE_COLOUR, logo="github")]
    svgs += [shield(label, value, VALUE_COLOUR, LABEL_COLOUR) for label, value in values]
    description = f"{TITLE}: " + ", ".join(f"{label} {value}" for label, value in values)
    with open(out, "w", encoding="utf-8") as f:
        f.write(stack(svgs, description))
    print(description)


if __name__ == "__main__":
    main()
