#!/usr/bin/env python3
"""Build public, past-year GitHub activity from GitHub's contribution data."""

import argparse
import json
import subprocess
from datetime import datetime, timezone
from html import escape
from pathlib import Path


QUERY = """query {
  user(login: "keyvanarasteh") {
    contributionsCollection {
      totalCommitContributions
      totalPullRequestContributions
      contributionCalendar {
        totalContributions
        weeks { contributionDays { date contributionCount } }
      }
    }
  }
}"""


def get_activity():
    response = subprocess.run(
        ["gh", "api", "graphql", "-f", f"query={QUERY}"],
        check=True, capture_output=True, text=True,
    )
    payload = json.loads(response.stdout)
    if payload.get("errors"):
        raise RuntimeError(f"GitHub GraphQL returned errors: {payload['errors']}")
    collection = payload["data"]["user"]["contributionsCollection"]
    calendar = collection["contributionCalendar"]
    days = [day for week in calendar["weeks"] for day in week["contributionDays"]]
    if not days or any(day["contributionCount"] < 0 for day in days):
        raise ValueError("GitHub returned an invalid contribution calendar")
    active = sum(day["contributionCount"] > 0 for day in days)
    streak = longest = 0
    for day in days:
        streak = streak + 1 if day["contributionCount"] else 0
        longest = max(longest, streak)
    counts = sorted(day["contributionCount"] for day in days if day["contributionCount"])
    thresholds = [counts[round((len(counts) - 1) * p)] for p in (.25, .5, .75)] if counts else [0, 0, 0]
    return {
        "updatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "periodStart": days[0]["date"], "periodEnd": days[-1]["date"],
        "contributions": calendar["totalContributions"],
        "commits": collection["totalCommitContributions"],
        "pullRequests": collection["totalPullRequestContributions"],
        "activeDays": active, "longestStreak": longest,
        "thresholds": thresholds,
        "weeks": [[{"date": day["date"], "count": day["contributionCount"]} for day in week["contributionDays"]] for week in calendar["weeks"]],
    }


def level(count, thresholds):
    if count == 0:
        return 0
    return 1 + sum(count > threshold for threshold in thresholds)


def render_svg(data):
    colors = ("#243443", "#456b49", "#668f54", "#8fc45e", "#b8f171")
    metrics = (
        ("CONTRIBUTIONS", data["contributions"]),
        ("ACTIVE DAYS", data["activeDays"]),
        ("COMMITS", data["commits"]),
        ("PULL REQUESTS", data["pullRequests"]),
    )
    parts = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="960" height="344" viewBox="0 0 960 344" role="img" aria-labelledby="title desc">',
        '<title id="title">Keyvan Arasteh GitHub activity, past year</title>',
        f'<desc id="desc">{data["contributions"]:,} contributions, {data["activeDays"]} active days, {data["commits"]:,} commit contributions, and {data["pullRequests"]:,} pull request contributions. Updated {escape(data["updatedAt"])}.</desc>',
        '<rect width="960" height="344" rx="16" fill="#101b27"/>',
        '<rect x="1" y="1" width="958" height="342" rx="15" fill="none" stroke="#314556"/>',
        '<text x="30" y="39" fill="#b8f171" font-family="Arial,sans-serif" font-size="12" font-weight="700" letter-spacing="2">GITHUB / ACTIVITY SIGNAL</text>',
        '<text x="930" y="39" fill="#91a5b3" font-family="Arial,sans-serif" font-size="12" text-anchor="end">PAST YEAR</text>',
    ]
    for index, (label, value) in enumerate(metrics):
        x = 30 + index * 230
        parts.extend((
            f'<text x="{x}" y="91" fill="#f3f7f2" font-family="Arial,sans-serif" font-size="35" font-weight="700">{value:,}</text>',
            f'<text x="{x}" y="113" fill="#91a5b3" font-family="Arial,sans-serif" font-size="11" font-weight="700" letter-spacing="1.2">{label}</text>',
        ))
    parts.append('<path d="M30 136H930" stroke="#314556"/>')
    parts.append('<text x="30" y="163" fill="#91a5b3" font-family="Arial,sans-serif" font-size="11" font-weight="700" letter-spacing="1.2">DAILY CONTRIBUTIONS</text>')
    all_weeks = data["weeks"]
    if len(all_weeks) > 54:
        raise ValueError("Unexpectedly long contribution calendar")
    step = 13
    x0 = 30
    for column, week in enumerate(all_weeks):
        for day in week:
            weekday = (datetime.fromisoformat(day["date"]).weekday() + 1) % 7
            x, y = x0 + column * step, 178 + weekday * step
            fill = colors[level(day["count"], data["thresholds"])]
            parts.append(f'<rect x="{x}" y="{y}" width="10" height="10" rx="2" fill="{fill}"/>')
    parts.extend((
        f'<text x="30" y="300" fill="#f3f7f2" font-family="Arial,sans-serif" font-size="13">Longest streak: <tspan fill="#b8f171" font-weight="700">{data["longestStreak"]} days</tspan></text>',
        f'<text x="930" y="300" fill="#91a5b3" font-family="Arial,sans-serif" font-size="11" text-anchor="end">Updated {escape(data["updatedAt"][:16].replace("T", " "))} UTC</text>',
        '<text x="30" y="327" fill="#91a5b3" font-family="Arial,sans-serif" font-size="10">Source: GitHub contribution calendar · counts follow GitHub contribution rules</text>',
        '</svg>',
    ))
    return "\n".join(parts) + "\n"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", type=Path)
    parser.add_argument("--svg", type=Path)
    args = parser.parse_args()
    if not args.json and not args.svg:
        parser.error("provide --json, --svg, or both")
    data = get_activity()
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(data, separators=(",", ":")) + "\n")
    if args.svg:
        args.svg.parent.mkdir(parents=True, exist_ok=True)
        args.svg.write_text(render_svg(data))
    print(f"Activity updated: {data['contributions']:,} contributions across {data['activeDays']} active days")


if __name__ == "__main__":
    main()
