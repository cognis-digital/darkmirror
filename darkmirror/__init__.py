"""DARKMIRROR -- surface-web mirror of a public Tor leak-site index.

DARKMIRROR ingests a periodically-published, surface-web JSON snapshot of
ransomware/extortion leak-site posts (the kind of feed projects like
ransomwatch publish to GitHub) and turns it into a brand-monitoring engine.

It does NOT touch Tor or the dark web directly. It works exclusively against
the sanitized, public, surface-web mirror -- which is what makes it safe to
run anywhere with zero install and the standard library only.

Capabilities:
  * Normalize and de-duplicate raw leak posts.
  * Match posts against a watchlist of brand/domain terms (with fuzzy and
    domain-aware matching) to surface likely victim mentions.
  * Diff two snapshots to find newly-appeared posts (the actual monitoring
    signal an analyst wants: "what is new since last poll").
  * Produce per-group and per-day statistics.
"""
from .core import (
    Post,
    Match,
    load_posts,
    normalize_posts,
    match_watchlist,
    diff_snapshots,
    summarize,
)

TOOL_NAME = "darkmirror"
TOOL_VERSION = "1.0.0"

__all__ = [
    "Post",
    "Match",
    "load_posts",
    "normalize_posts",
    "match_watchlist",
    "diff_snapshots",
    "summarize",
    "TOOL_NAME",
    "TOOL_VERSION",
]
