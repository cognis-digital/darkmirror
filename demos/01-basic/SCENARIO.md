# DARKMIRROR demo 01 -- basic brand monitoring

## Scenario

You run threat-intel for a company. Every few hours you pull the public,
surface-web mirror of the Tor extortion-leak index (the kind of sanitized
JSON snapshot projects like `ransomwatch` publish to GitHub). You never touch
Tor yourself -- you only read the public mirror.

You want to answer three questions from a snapshot:

1. **Are any of my brands / suppliers mentioned?**  (`watch`)
2. **What appeared that's new since my last poll?**  (`diff`)
3. **What's the overall posting landscape right now?**  (`stats`)

## Files

- `snapshot.json`     -- the current public mirror snapshot.
- `snapshot_prev.json` -- the snapshot from your previous poll (for diffing).
- `watchlist.txt`     -- brands / domains you care about.

The watchlist deliberately includes `acme-corp.com` (an exact domain victim),
`Globex` (a fuzzy/label match against `globex-industries`), and
`initech.io` (a supplier that is NOT in the current snapshot, to show clean
non-matches).

## Run it

```bash
# 1. Brand watch (human-readable)
python -m darkmirror watch demos/01-basic/snapshot.json -w demos/01-basic/watchlist.txt

# 2. Brand watch as JSON (for piping into a SIEM / ticketing system)
python -m darkmirror --format json watch demos/01-basic/snapshot.json -w demos/01-basic/watchlist.txt

# 3. What is new since the previous poll?
python -m darkmirror diff demos/01-basic/snapshot_prev.json demos/01-basic/snapshot.json

# 4. Landscape stats
python -m darkmirror stats demos/01-basic/snapshot.json
```

## Expected

- `watch` surfaces `acme-corp.com` (domain hit, score 1.00) and `Globex`
  (label/fuzzy hit). `initech.io` produces no match.
- `diff` reports the `globex-industries` and `northwind-traders` posts as
  **added** (they are absent from the previous snapshot).
- `stats` shows `lockbit3` as the busiest group.
