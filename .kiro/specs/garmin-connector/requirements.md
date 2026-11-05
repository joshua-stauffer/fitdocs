# Requirements Document

## Project Description (Input)
An athlete who records on Garmin creates their own key for Garmin's Connect
Personal API, connects it once with `fitdocs connect garmin`, and from then on
`fitdocs pull` brings their activities and daily wellness straight from Garmin,
history included, into the same inbox a hand-dropped file lands in. There is no
relay, no data export and no intervals.icu account. The connector is built into
the `fitdocs` wheel, uses the standard library only through
`fitdocs.connectors.http`, is read-only at Garmin, and never sends the key
anywhere but Garmin's token call. Women's health, courses and training are out.
It derives only from Garmin's public Personal API material and from measurement.
Source: `.kiro/specs/garmin-connector/brief.md`; Phase 15 of
`.kiro/steering/roadmap.md`.

## Requirements
<!-- Will be generated in /kiro-spec-requirements phase -->
