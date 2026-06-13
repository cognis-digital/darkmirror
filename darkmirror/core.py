"""Core engine for DARKMIRROR.

Pure standard library. No network. All functions operate on already-fetched
surface-web JSON snapshots so the engine is deterministic and testable.

Snapshot format (a list of post objects, matching the public ransomwatch-style
feed). Each post is tolerant of missing fields:

    {
      "post_title": "acme-corp.com",
      "group_name": "lockbit3",
      "discovered": "2024-03-01 12:30:55.000000",
      "description": "All internal documents will be published...",
      "website": "http://lockbit...onion"
    }

The canonical key field varies across feeds, so we accept several aliases.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, date
from difflib import SequenceMatcher
from typing import Any, Iterable

# ---- field aliasing -------------------------------------------------------

_TITLE_KEYS = ("post_title", "title", "victim", "name", "company")
_GROUP_KEYS = ("group_name", "group", "actor", "gang")
_DATE_KEYS = ("discovered", "date", "published", "timestamp", "first_seen")
_DESC_KEYS = ("description", "desc", "summary", "text")
_SITE_KEYS = ("website", "url", "link", "source")

_DATE_FORMATS = (
    "%Y-%m-%d %H:%M:%S.%f",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%dT%H:%M:%S.%f",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%dT%H:%M:%SZ",
    "%Y-%m-%d",
    "%d/%m/%Y",
)

_DOMAIN_RE = re.compile(r"\b([a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z]{2,})+)\b")


def _first(obj: dict, keys: Iterable[str]) -> str:
    for k in keys:
        v = obj.get(k)
        if v is not None and str(v).strip():
            return str(v).strip()
    return ""


def _parse_date(raw: str) -> datetime | None:
    raw = (raw or "").strip()
    if not raw:
        return None
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue
    # last resort: leading ISO-ish date
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", raw)
    if m:
        try:
            return datetime(int(m[1]), int(m[2]), int(m[3]))
        except ValueError:
            return None
    return None


# ---- data model -----------------------------------------------------------


@dataclass(frozen=True)
class Post:
    title: str
    group: str
    discovered: datetime | None
    description: str
    website: str

    @property
    def fingerprint(self) -> str:
        """Stable identity for de-dup / diffing: title + group only.

        Re-posts with jittered timestamps or edited descriptions still collapse
        to one logical victim entry.
        """
        basis = f"{self.title.lower().strip()}|{self.group.lower().strip()}"
        return hashlib.sha1(basis.encode("utf-8")).hexdigest()[:16]

    @property
    def day(self) -> date | None:
        return self.discovered.date() if self.discovered else None

    def to_dict(self) -> dict[str, Any]:
        return {
            "fingerprint": self.fingerprint,
            "title": self.title,
            "group": self.group,
            "discovered": self.discovered.isoformat() if self.discovered else None,
            "description": self.description,
            "website": self.website,
        }


@dataclass
class Match:
    term: str
    post: Post
    score: float
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "term": self.term,
            "score": round(self.score, 3),
            "reason": self.reason,
            "post": self.post.to_dict(),
        }


# ---- loading / normalization ---------------------------------------------


def load_posts(path: str) -> list[Post]:
    """Load a snapshot JSON file from disk and normalize it."""
    with open(path, "r", encoding="utf-8") as fh:
        raw = json.load(fh)
    return normalize_posts(raw)


def normalize_posts(raw: Any) -> list[Post]:
    """Turn raw feed JSON into a de-duplicated list of Post objects.

    Accepts either a bare list of post dicts or an object with a "posts"
    (or "data") array.
    """
    if isinstance(raw, dict):
        for key in ("posts", "data", "entries", "items"):
            if isinstance(raw.get(key), list):
                raw = raw[key]
                break
    if not isinstance(raw, list):
        raise ValueError("snapshot must be a JSON array of posts (or an object containing one)")

    seen: dict[str, Post] = {}
    for item in raw:
        if not isinstance(item, dict):
            continue
        title = _first(item, _TITLE_KEYS)
        group = _first(item, _GROUP_KEYS)
        if not title and not group:
            continue
        post = Post(
            title=title,
            group=group,
            discovered=_parse_date(_first(item, _DATE_KEYS)),
            description=_first(item, _DESC_KEYS),
            website=_first(item, _SITE_KEYS),
        )
        fp = post.fingerprint
        prior = seen.get(fp)
        # keep the earliest discovery (the real first-seen)
        if prior is None:
            seen[fp] = post
        elif post.discovered and (prior.discovered is None or post.discovered < prior.discovered):
            seen[fp] = post
    out = list(seen.values())
    out.sort(key=lambda p: (p.discovered or datetime.max, p.group, p.title))
    return out


# ---- watchlist matching ---------------------------------------------------


def _domains_in(text: str) -> set[str]:
    return set(_DOMAIN_RE.findall(text.lower()))


def _root_label(term: str) -> str:
    """Reduce a brand/domain term to a comparable label.

    'Acme Corp' -> 'acmecorp'; 'acme-corp.com' -> 'acmecorp'.
    """
    t = term.lower().strip()
    # strip a leading scheme / www
    t = re.sub(r"^https?://", "", t)
    t = re.sub(r"^www\.", "", t)
    # if it looks like a domain, take the registrable-ish label (second-last segment)
    if "." in t and _DOMAIN_RE.search(t):
        parts = t.split("/")[0].split(".")
        if len(parts) >= 2:
            t = parts[-2]
    return re.sub(r"[^a-z0-9]", "", t)


def match_watchlist(
    posts: list[Post],
    terms: Iterable[str],
    threshold: float = 0.82,
) -> list[Match]:
    """Match posts against watchlist terms.

    Matching strategy, strongest first:
      1. Exact domain hit in title/description/website  (score 1.0).
      2. Brand label appears as a token/substring in the title (score 0.95).
      3. Fuzzy similarity of the brand label vs the post-title label, if it
         clears ``threshold``.
    """
    matches: list[Match] = []
    norm_terms = [(raw, _root_label(raw), raw.lower().strip()) for raw in terms]
    norm_terms = [t for t in norm_terms if t[1]]

    for post in posts:
        haystack = " ".join((post.title, post.description, post.website)).lower()
        post_domains = _domains_in(haystack)
        title_label = _root_label(post.title)

        best: Match | None = None
        for raw, label, lowterm in norm_terms:
            score = 0.0
            reason = ""
            # 1. domain match
            if "." in lowterm:
                dom = lowterm.split("/")[0].replace("www.", "")
                if dom in post_domains or any(d == dom or d.endswith("." + dom) for d in post_domains):
                    score, reason = 1.0, f"domain '{dom}' present"
            # 2. label token / substring in title
            if score < 0.95 and label and (label in title_label or label in re.sub(r"[^a-z0-9]", "", haystack)):
                if score < 0.95:
                    score, reason = 0.95, f"brand label '{label}' in post"
            # 3. fuzzy on the title label
            if score < threshold and label and title_label:
                ratio = SequenceMatcher(None, label, title_label).ratio()
                if ratio >= threshold and ratio > score:
                    score, reason = ratio, f"fuzzy title match ({ratio:.2f})"
            if score >= threshold and (best is None or score > best.score):
                best = Match(term=raw, post=post, score=score, reason=reason)
        if best is not None:
            matches.append(best)

    matches.sort(key=lambda m: (-m.score, m.post.discovered or datetime.max))
    return matches


# ---- diffing --------------------------------------------------------------


def diff_snapshots(old: list[Post], new: list[Post]) -> dict[str, list[Post]]:
    """Compare two normalized snapshots.

    Returns added/removed posts keyed by fingerprint identity. 'added' is the
    monitoring signal: posts present in ``new`` but not in ``old``.
    """
    old_fp = {p.fingerprint: p for p in old}
    new_fp = {p.fingerprint: p for p in new}
    added = [new_fp[fp] for fp in new_fp.keys() - old_fp.keys()]
    removed = [old_fp[fp] for fp in old_fp.keys() - new_fp.keys()]
    added.sort(key=lambda p: (p.discovered or datetime.max, p.title))
    removed.sort(key=lambda p: (p.discovered or datetime.max, p.title))
    return {"added": added, "removed": removed}


# ---- stats ----------------------------------------------------------------


def summarize(posts: list[Post]) -> dict[str, Any]:
    by_group: dict[str, int] = {}
    by_day: dict[str, int] = {}
    dated = 0
    for p in posts:
        by_group[p.group or "(unknown)"] = by_group.get(p.group or "(unknown)", 0) + 1
        if p.day:
            dated += 1
            d = p.day.isoformat()
            by_day[d] = by_day.get(d, 0) + 1
    top_groups = sorted(by_group.items(), key=lambda kv: (-kv[1], kv[0]))
    return {
        "total_posts": len(posts),
        "dated_posts": dated,
        "distinct_groups": len(by_group),
        "top_groups": [{"group": g, "count": c} for g, c in top_groups[:15]],
        "posts_by_day": dict(sorted(by_day.items())),
    }
