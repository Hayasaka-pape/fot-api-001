These are reduced factual payloads for offline schema regression tests, not live or demo data delivered by the app.

- `match_reference.json`, `date_reference.json`: selected fields from bjrsti/fotmob's MIT-licensed VCR cassettes recorded 2026-05-16.
- `team_current.json`, `league_current.json`: reduced public FotMob API responses fetched 2026-10-07 (`teams?id=8455`, `leagues?id=47&tab=overview`). Only a few rows and participants are retained.
- `match_on_pitch_5315746.json`, `match_on_pitch_5181855.json`: exact, unmodified selected upstream branches (`general`, header teams/status/events, content lineup and matchFacts events), fetched 2026-10-07. They preserve every starter/sub ID, full substitution timeline, performance summary, and a real YellowRed dismissal. These source snapshots are test evidence only; the app never serves them as live data.

The normalizer tests intentionally preserve real response nesting (periods, composite standings, squad groups, seasonal participants).
