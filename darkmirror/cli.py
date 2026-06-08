"""Command-line interface for DARKMIRROR.

Subcommands:
  watch    Match a snapshot against a brand watchlist.
  diff     Show posts newly added between an old and a new snapshot.
  stats    Summarize a snapshot (group / day breakdown).

Global:
  --version
  --format {table,json}   (default: table)

Returns 0 on success, non-zero on any error.
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from . import TOOL_NAME, TOOL_VERSION
from .core import load_posts, match_watchlist, diff_snapshots, summarize


def _read_terms(args) -> list[str]:
    terms: list[str] = list(args.term or [])
    if args.watchlist:
        with open(args.watchlist, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line and not line.startswith("#"):
                    terms.append(line)
    # de-dup, preserve order
    seen: set[str] = set()
    out = []
    for t in terms:
        k = t.lower()
        if k not in seen:
            seen.add(k)
            out.append(t)
    return out


def _emit(payload: dict[str, Any], fmt: str, table_lines: list[str]) -> None:
    if fmt == "json":
        json.dump(payload, sys.stdout, indent=2, default=str)
        sys.stdout.write("\n")
    else:
        sys.stdout.write("\n".join(table_lines) + ("\n" if table_lines else ""))


def _cmd_watch(args) -> int:
    terms = _read_terms(args)
    if not terms:
        print("error: provide at least one --term or a --watchlist file", file=sys.stderr)
        return 2
    posts = load_posts(args.snapshot)
    matches = match_watchlist(posts, terms, threshold=args.threshold)
    payload = {
        "tool": TOOL_NAME,
        "version": TOOL_VERSION,
        "command": "watch",
        "snapshot": args.snapshot,
        "terms": terms,
        "scanned_posts": len(posts),
        "match_count": len(matches),
        "matches": [m.to_dict() for m in matches],
    }
    lines = [f"DARKMIRROR watch -- {len(matches)} match(es) across {len(posts)} posts"]
    for m in matches:
        when = m.post.discovered.date().isoformat() if m.post.discovered else "????-??-??"
        lines.append(
            f"  [{m.score:4.2f}] {m.term:<22} {m.post.group:<14} {when}  {m.post.title}  ({m.reason})"
        )
    if not matches:
        lines.append("  (no watchlist hits)")
    _emit(payload, args.format, lines)
    return 0


def _cmd_diff(args) -> int:
    old = load_posts(args.old)
    new = load_posts(args.new)
    result = diff_snapshots(old, new)
    payload = {
        "tool": TOOL_NAME,
        "version": TOOL_VERSION,
        "command": "diff",
        "old": args.old,
        "new": args.new,
        "added_count": len(result["added"]),
        "removed_count": len(result["removed"]),
        "added": [p.to_dict() for p in result["added"]],
        "removed": [p.to_dict() for p in result["removed"]],
    }
    lines = [
        f"DARKMIRROR diff -- +{len(result['added'])} new / -{len(result['removed'])} gone",
        "  ADDED (new since old snapshot):",
    ]
    for p in result["added"]:
        when = p.discovered.date().isoformat() if p.discovered else "????-??-??"
        lines.append(f"    + {p.group:<14} {when}  {p.title}")
    if not result["added"]:
        lines.append("    (none)")
    lines.append("  REMOVED:")
    for p in result["removed"]:
        when = p.discovered.date().isoformat() if p.discovered else "????-??-??"
        lines.append(f"    - {p.group:<14} {when}  {p.title}")
    if not result["removed"]:
        lines.append("    (none)")
    _emit(payload, args.format, lines)
    return 0


def _cmd_stats(args) -> int:
    posts = load_posts(args.snapshot)
    summary = summarize(posts)
    payload = {
        "tool": TOOL_NAME,
        "version": TOOL_VERSION,
        "command": "stats",
        "snapshot": args.snapshot,
        **summary,
    }
    lines = [
        f"DARKMIRROR stats -- {summary['total_posts']} posts / "
        f"{summary['distinct_groups']} groups / {summary['dated_posts']} dated",
        "  Top groups:",
    ]
    for row in summary["top_groups"]:
        lines.append(f"    {row['count']:>4}  {row['group']}")
    _emit(payload, args.format, lines)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog=TOOL_NAME,
        description="Surface-web mirror of a public Tor leak-site index for brand monitoring.",
    )
    p.add_argument("--version", action="version", version=f"{TOOL_NAME} {TOOL_VERSION}")
    p.add_argument(
        "--format",
        choices=("table", "json"),
        default="table",
        help="output format (default: table)",
    )
    sub = p.add_subparsers(dest="command", required=True)

    w = sub.add_parser("watch", help="match a snapshot against a brand watchlist")
    w.add_argument("snapshot", help="path to a surface-web leak-index snapshot (JSON)")
    w.add_argument("-t", "--term", action="append", help="a brand/domain term (repeatable)")
    w.add_argument("-w", "--watchlist", help="file with one brand/domain term per line")
    w.add_argument("--threshold", type=float, default=0.82, help="fuzzy match threshold 0-1")
    w.set_defaults(func=_cmd_watch)

    d = sub.add_parser("diff", help="show posts newly added between two snapshots")
    d.add_argument("old", help="older snapshot JSON")
    d.add_argument("new", help="newer snapshot JSON")
    d.set_defaults(func=_cmd_diff)

    s = sub.add_parser("stats", help="summarize a snapshot")
    s.add_argument("snapshot", help="snapshot JSON")
    s.set_defaults(func=_cmd_stats)
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except FileNotFoundError as e:
        print(f"error: file not found: {e.filename}", file=sys.stderr)
        return 1
    except (ValueError, json.JSONDecodeError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
