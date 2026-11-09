# AI event type pilot — 2026-11-09

Pilot for #486: suggested `ado:hasEventTypeConcept` values for 100 untyped Artsdata core events (Nov 9–13, 2026), classified against `adr:ArtsdataEventTypes` v4.0.

- `ai-event-types-pilot.ttl` — the suggestions as a separate source graph. Turtle with RDF 1.2 `{| |}` annotations: run, confidence and rationale on each claim. Parses with pyoxigraph (467 triples).
- `ai-event-types-review.csv` — the review sheet, sorted with no-suggestion rows first, then lowest confidence first. Fill in `decision`, `corrected_type` and `reviewer`.
- `classify.py` — regenerates both files from the classifications embedded in it.

Inputs used: name, first 220 chars of description, `schema:additionalType`, organizer name, venue name. **Performer and type history were not used**; see #486 for why they should be.

Classifications were made by Claude reading the event records in a chat session, not by an automated API run. Not loaded into Artsdata.

Results: 67 at ≥0.85 confidence, 17 at 0.70–0.84, 8 below 0.70, 8 with no suggestion. `ado:confidence` is a proposed term.
