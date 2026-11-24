# crowstheatre

Converts the Crow's Theatre schedule to schema.org JSON-LD for Artsdata. Run by
`.github/workflows/crowstheatre-com.yml`.

- Source: `https://www.crowstheatre.com/shows-events/schedule` (one month per
  page) and the show pages it links to. The site publishes no JSON-LD.
- Output: `output/crowstheatre-com-events.jsonld`
- Graph: `http://kg.artsdata.ca/culture-creates/artsdata-orion-api/crowstheatre-com`

```bash
pip install -r src/crowstheatre/requirements.txt
python src/crowstheatre/main.py                  # live site
python src/crowstheatre/main.py --cache pages/   # save pages, and reuse saved ones
```

The mapping decisions (event @ids, dates, venues, event types, offers) are
documented at the top of `main.py`.

## Footlight

Crow's Theatre events also reach Artsdata through Footlight, in
`http://kg.artsdata.ca/culture-creates/footlight/crowstheatre-com`. Both are
kept for now, to compare them, so **leave auto-minting off** for this graph
until one is retired.

## When a run fails or warns

The script writes nothing when the site no longer looks as expected: a schedule
row it can't read, a date that disagrees with its ticket button, a month that
isn't complete, or fewer than half the events still upcoming in the last
output. If a drop is real, dispatch the workflow with `allow-drop`.

Warnings appear on the GitHub run page and don't stop the run:

- `Venue ... is not in VENUES`: look the venue up in Artsdata and add it.
- `Cabaret show ... is not in CABARET_TYPES`: add its event type.
- `Unknown ticket button`: the event goes out without an Offer.
- `No description found on ...`
- `No performances listed for ...` or `Skipping duplicate row`
