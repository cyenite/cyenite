#!/usr/bin/env python3
import os
import json
import math
import time
import http.client
import urllib.error
import urllib.request
from pathlib import Path
from statistics import mean
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

RISE = 0.4
FALL = 0.3
WINDOW = 120
API = "https://api.github.com/graphql"
ROOT = Path(__file__).resolve().parent.parent
FONT = "ui-monospace,SFMono-Regular,Menlo,Consolas,'Liberation Mono',monospace"
QUERY = """
query($login: String!) {
  user(login: $login) {
    contributionsCollection { contributionCalendar { weeks { contributionDays { date contributionCount } } } }
    repositories(first: 100, ownerAffiliations: OWNER, privacy: PUBLIC, isFork: false, orderBy: {field: CREATED_AT, direction: DESC}) {
      nodes { name createdAt isPrivate }
    }
  }
}
"""


@dataclass(frozen=True)
class Day:
    count: int
    on: date


@dataclass(frozen=True)
class Launch:
    name: str
    on: date


@dataclass(frozen=True)
class Candle:
    low: float
    high: float
    open: float
    close: float
    volume: int
    on: date

    @property
    def is_up(self):
        return self.close >= self.open


@dataclass(frozen=True)
class Theme:
    fg: str
    ma: str
    up: str
    ink: str
    down: str
    grid: str
    muted: str
    accent: str


DARK = Theme(fg="#f0f6fc", ma="#d29922", up="#3fb950", ink="#0d1117", down="#f85149", grid="rgba(240,246,252,0.1)", muted="#9198a1", accent="#4493f8")
LIGHT = Theme(fg="#1f2328", ma="#9a6700", up="#1a7f37", ink="#ffffff", down="#d1242f", grid="rgba(31,35,40,0.1)", muted="#59636e", accent="#0969da")


@dataclass(frozen=True)
class Activity:
    login: str
    now: datetime
    days: list[Day]
    launches: list[Launch]

    @property
    def total(self):
        return sum(d.count for d in self.days)

    @property
    def best(self):
        return max(self.days, key=lambda d: d.count)

    @property
    def momentum(self):
        counts = [d.count for d in self.days]
        recent, previous = sum(counts[-28:]), sum(counts[-56:-28])
        return recent / previous - 1 if previous else None

    @property
    def streak(self):
        days = self.days[:-1] if not self.days[-1].count else self.days
        streak = 0
        for day in reversed(days):
            if not day.count:
                break
            streak += 1
        return streak

    @property
    def longest(self):
        longest = run = 0
        for day in self.days:
            run = run + 1 if day.count else 0
            longest = max(longest, run)
        return longest

    def candles(self):
        level = mean(math.log1p(d.count) for d in self.days[:7])
        candles = []
        for day in self.days:
            previous, value = level, math.log1p(day.count)
            level += (RISE if value > level else FALL) * (value - level)
            top, bottom = max(previous, level), min(previous, level)
            high = top + RISE * max(0, value - top)
            low = bottom - FALL * max(0, bottom - value)
            candles.append(Candle(low=math.expm1(low), high=math.expm1(high), open=math.expm1(previous), close=math.expm1(level), volume=day.count, on=day.on))
        return candles


def call(login):
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "activity-chart"}
    if token := os.environ.get("GITHUB_TOKEN"):
        headers["Authorization"] = f"Bearer {token}"
    body = json.dumps({"query": QUERY, "variables": {"login": login}}).encode()
    for attempt in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(API, data=body, headers=headers), timeout=30) as response:
                result = json.load(response)
            break
        except (TimeoutError, http.client.IncompleteRead, urllib.error.URLError):
            if attempt == 2:
                raise
            time.sleep(2 ** attempt)
    if result.get("errors"):
        raise RuntimeError(result["errors"])
    return result["data"]["user"]


def fetch(login, now):
    user = call(login)
    weeks = user["contributionsCollection"]["contributionCalendar"]["weeks"]
    days = [Day(count=d["contributionCount"], on=date.fromisoformat(d["date"])) for w in weeks for d in w["contributionDays"]]
    days = [d for d in days if d.on <= now.date()]
    nodes = [n for n in user["repositories"]["nodes"] if not n["isPrivate"]]
    launches = [Launch(name=n["name"], on=date.fromisoformat(n["createdAt"][:10])) for n in nodes]
    return Activity(login=login, now=now, days=days, launches=[l for l in launches if l.on >= days[0].on])


def short(on):
    return f"{on.strftime('%b')} {on.day}"


STYLE = (
    ".c{animation:rise .5s ease-out backwards}"
    "@keyframes rise{from{opacity:0;transform:translateY(10px)}}"
    ".v{transform-box:fill-box;transform-origin:50% 100%;animation:grow .6s ease-out backwards}"
    "@keyframes grow{from{transform:scaleY(0)}}"
    ".ma{stroke-dasharray:1;animation:draw 1.6s 1s ease-out backwards}"
    "@keyframes draw{from{stroke-dashoffset:1}}"
    ".m{animation:drop .5s 2.2s cubic-bezier(.3,1.6,.6,1) backwards}"
    "@keyframes drop{from{opacity:0;transform:translateY(-10px)}}"
    ".tick{transform-box:fill-box;animation:tick 2.6s 2s ease-in-out infinite}"
    "@keyframes tick{25%{transform:scaleY(.78)}50%{transform:scaleY(1.12)}75%{transform:scaleY(.92)}}"
    ".px{animation:march 1.4s linear infinite}"
    "@keyframes march{to{stroke-dashoffset:-14}}"
    ".scan{animation:scan 9s 3s linear infinite backwards}"
    "@keyframes scan{from{transform:translateX(-80px)}to{transform:translateX(800px)}}"
    ".pulse{transform-box:fill-box;transform-origin:center;animation:pulse 2s ease-out infinite}"
    "@keyframes pulse{from{transform:scale(1);opacity:.8}to{transform:scale(3.4);opacity:0}}"
    "@media (prefers-reduced-motion:reduce){.c,.v,.ma,.m,.tick,.px,.scan,.pulse{animation:none}.glint,.scan{display:none}}"
)


def chart(activity, theme):
    width, height = 840, 476
    left, right, top, bottom, base = 24, 744, 156, 316, 376
    candles = activity.candles()
    closes = [c.close for c in candles]
    averages = [mean(closes[max(0, i - 19):i + 1]) for i in range(len(closes))][-WINDOW:]
    candles = candles[-WINDOW:]
    floor, ceiling = min(c.low for c in candles), max(c.high for c in candles)
    pad = (ceiling - floor) * 0.08 or 1
    floor, ceiling = max(0, floor - pad), ceiling + pad
    step = (right - left) / len(candles)
    body = max(step * 0.62, 1.5)
    peak = max(candles, key=lambda c: c.volume)
    live = candles[-1]
    momentum = activity.momentum
    tone = theme.up if momentum is None or momentum >= 0 else theme.down
    trend = "NO PRIOR DATA" if momentum is None else f"{'▲' if momentum >= 0 else '▼'} {momentum * 100:+.1f}% VS PREVIOUS 4 WEEKS"

    def x(index):
        return left + step * index + step / 2

    def y(value):
        return top + (ceiling - value) / (ceiling - floor) * (bottom - top)

    close = y(live.close)
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" font-family="{FONT}">',
        f"<style>{STYLE}</style>",
        f'<defs><linearGradient id="sweep" x1="0" x2="1"><stop offset="0" stop-color="{theme.accent}" stop-opacity="0"/>'
        f'<stop offset=".5" stop-color="{theme.accent}" stop-opacity=".09"/><stop offset="1" stop-color="{theme.accent}" stop-opacity="0"/></linearGradient>'
        f'<clipPath id="plot"><rect x="{left}" y="{top - 10}" width="{right - left}" height="{base - top + 10}"/></clipPath></defs>',
        f'<text x="24" y="46" font-size="26" font-weight="700" fill="{theme.fg}">{activity.login}</text>',
        f'<text x="24" y="70" font-size="12" letter-spacing="1" fill="{theme.muted}">GITHUB CONTRIBUTIONS · DAILY CANDLES · LAST {WINDOW} DAYS</text>',
        f'<circle class="pulse" cx="29" cy="88" r="3.5" fill="{theme.up}"/><circle cx="29" cy="88" r="3.5" fill="{theme.up}"/>',
        f'<text x="40" y="92" font-size="11" fill="{theme.muted}"><tspan fill="{theme.up}" font-weight="700">LIVE</tspan> · UPDATED {activity.now.strftime("%Y-%m-%d %H:%M")} UTC</text>',
        f'<text x="816" y="46" font-size="26" font-weight="700" text-anchor="end" fill="{theme.fg}">{activity.total:,}</text>',
        f'<text x="816" y="70" font-size="12" letter-spacing="1" text-anchor="end" fill="{theme.muted}">IN THE LAST 12 MONTHS</text>',
        f'<text x="816" y="92" font-size="11" text-anchor="end" fill="{tone}">{trend}</text>',
        f'<text x="{right + 10}" y="{top - 10}" font-size="10" fill="{theme.muted}">PER DAY</text>',
    ]
    for index in range(5):
        level = floor + (ceiling - floor) * index / 4
        parts.append(f'<line x1="{left}" x2="{right}" y1="{y(level):.1f}" y2="{y(level):.1f}" stroke="{theme.grid}"/>')
        if abs(y(level) - close) > 14:
            parts.append(f'<text x="{right + 10}" y="{y(level) + 4:.1f}" font-size="11" fill="{theme.muted}">{level:.1f}</text>')
    parts.append(f'<g clip-path="url(#plot)"><rect class="scan" x="{left}" y="{top}" width="80" height="{base - top}" fill="url(#sweep)"/></g>')
    month = candles[0].on.month
    for index, candle in enumerate(candles):
        color = theme.up if candle.is_up else theme.down
        upper, lower = y(max(candle.open, candle.close)), y(min(candle.open, candle.close))
        bar = candle.volume / (peak.volume or 1) * 48
        delay = f"animation-delay:{index * 0.012:.3f}s"
        origin = "50% 100%" if candle.is_up else "50% 0%"
        tick = f' class="tick" style="transform-origin:{origin}"' if candle is live else ""
        parts.append(
            f'<g class="c" style="{delay}">'
            f'<line x1="{x(index):.1f}" x2="{x(index):.1f}" y1="{y(candle.high):.1f}" y2="{y(candle.low):.1f}" stroke="{color}"/>'
            f'<rect{tick} x="{x(index) - body / 2:.1f}" y="{upper:.1f}" width="{body:.1f}" height="{max(lower - upper, 1.2):.1f}" fill="{color}"/>'
            "</g>"
            f'<rect class="v" style="{delay}" x="{x(index) - body / 2:.1f}" y="{base - bar:.1f}" width="{body:.1f}" height="{bar:.1f}" fill="{color}" opacity=".35"/>'
        )
        if candle.on.month != month:
            parts.append(f'<text x="{x(index):.1f}" y="394" font-size="11" text-anchor="middle" fill="{theme.muted}">{candle.on.strftime("%b").upper()}</text>')
        month = candle.on.month
    points = [(x(i), y(a)) for i, a in enumerate(averages)]
    path = "M" + " L".join(f"{px:.1f} {py:.1f}" for px, py in points)
    parts += [
        f'<path class="ma" d="{path}" pathLength="1" fill="none" stroke="{theme.ma}" stroke-width="1.5" stroke-linejoin="round"/>',
        f'<circle class="glint" r="3" fill="{theme.ma}" opacity="0"><animateMotion dur="8s" begin="2.8s" repeatCount="indefinite" path="{path}"/>'
        '<animate attributeName="opacity" values="0;1;1;0" keyTimes="0;.08;.92;1" dur="8s" begin="2.8s" repeatCount="indefinite"/></circle>',
    ]
    index = candles.index(peak)
    parts.append(f'<text class="m" x="{x(index):.1f}" y="{base - 52}" font-size="9" text-anchor="middle" fill="{theme.muted}">PEAK {peak.volume}</text>')
    parts += markers(activity.launches, candles, x, y, theme, left, right)
    parts += [
        f'<line class="px" x1="{left}" x2="{right}" y1="{close:.1f}" y2="{close:.1f}" stroke="{tone}" stroke-dasharray="3 4" opacity=".7"/>',
        f'<circle class="pulse" cx="{x(len(candles) - 1):.1f}" cy="{close:.1f}" r="3" fill="{tone}"/>',
        f'<rect x="{right + 4}" y="{close - 10:.1f}" width="64" height="20" rx="4" fill="{tone}"/>',
        f'<text x="{right + 36}" y="{close + 4:.1f}" font-size="11" font-weight="700" text-anchor="middle" fill="{theme.ink}">{live.close:.1f}</text>',
    ]
    best = activity.best
    stats = [
        ("CURRENT STREAK", f"{activity.streak} days"),
        ("LONGEST STREAK", f"{activity.longest} days"),
        ("BEST DAY", f"{best.count} · {short(best.on)}"),
        ("NEW REPOS", str(len(activity.launches))),
    ]
    parts.append(f'<line x1="24" x2="816" y1="408" y2="408" stroke="{theme.grid}"/>')
    for column, (label, value) in enumerate(stats):
        parts.append(f'<text x="{24 + column * 198}" y="428" font-size="10" letter-spacing="1" fill="{theme.muted}">{label}</text>')
        parts.append(f'<text x="{24 + column * 198}" y="447" font-size="15" font-weight="700" fill="{theme.fg}">{value}</text>')
    parts += [
        f'<text x="24" y="466" font-size="10" fill="{theme.muted}">CANDLE = 1 DAY OF THE LOG-WEIGHTED AVERAGE · BARS = DAILY TOTAL · '
        f'<tspan fill="{theme.ma}">MA20</tspan> · <tspan fill="{theme.accent}">◆ NEW PUBLIC REPO</tspan></text>',
        "</svg>",
    ]
    return "\n".join(parts)


def markers(launches, candles, x, y, theme, left, right):
    positions = {c.on: i for i, c in enumerate(candles)}
    groups = {}
    for launch in sorted(launches, key=lambda l: l.on):
        if launch.on >= candles[0].on:
            groups.setdefault(positions.get(launch.on, len(candles) - 1), []).append(launch)
    parts, rows = [], [left - 1, left - 1]
    for index, group in sorted(groups.items()):
        label = "+ " + " · ".join(l.name for l in group)
        size = len(label) * 6.6 + 14
        start = min(max(x(index) - size / 2, left), right - size)
        anchor = y(candles[index].high) - 8
        parts.append(f'<path class="m" d="M{x(index):.1f} {anchor - 4:.1f}l4 4-4 4-4-4z" fill="{theme.accent}"/>')
        row = next((r for r, end in enumerate(rows) if start > end + 6), None)
        if row is None:
            continue
        rows[row] = start + size
        chip = 106 + row * 22
        parts.append(
            f'<g class="m">'
            f'<line x1="{x(index):.1f}" x2="{x(index):.1f}" y1="{chip + 18}" y2="{anchor - 6:.1f}" stroke="{theme.accent}" stroke-dasharray="2 3" opacity=".6"/>'
            f'<rect x="{start:.1f}" y="{chip}" width="{size:.1f}" height="18" rx="9" fill="none" stroke="{theme.accent}"/>'
            f'<text x="{start + size / 2:.1f}" y="{chip + 13}" font-size="11" text-anchor="middle" fill="{theme.accent}">{label}</text>'
            "</g>"
        )
    return parts


def main():
    login = os.environ.get("ACTIVITY_LOGIN", "cyenite")
    activity = fetch(login, datetime.now(timezone.utc))
    assets = ROOT / "assets"
    assets.mkdir(exist_ok=True)
    (assets / "activity-dark.svg").write_text(chart(activity, DARK))
    (assets / "activity-light.svg").write_text(chart(activity, LIGHT))
    print(f"{login}: {activity.total:,} contributions, {len(activity.launches)} new public repos")


if __name__ == "__main__":
    main()
