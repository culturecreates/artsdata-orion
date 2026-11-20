# culture3r

Converts the Culture Trois-Rivières programmation feed to schema.org JSON-LD
for Artsdata. Run by `.github/workflows/culture3r-com-events.yml`.

- Source: `https://www.culture3r.com/wp/wp-admin/admin-ajax.php?action=dates`
  (public, undocumented; it feeds the Vue list on `/programmation/`, built by
  the agency STEREO, so it can change without notice).
- Output: `output/culture3r-com-events.jsonld`
- Graph: `http://kg.artsdata.ca/culture-creates/artsdata-orion/culture3r-com`

```bash
pip install -r src/culture3r/requirements.txt
python src/culture3r/main.py                     # live feed
python src/culture3r/main.py --input dates.json  # saved copy
```

The mapping decisions (skipped rows, event @ids, venues, event types, offers)
are documented at the top of `main.py`. When the site adds a venue, the script
logs `has no Artsdata ID in VENUES`: look the venue up in Artsdata and add it
to `VENUES`.

Not in the feed: descriptions, performer types (Person vs. group), and the
AudienceView ticket link (`billets.culture3r.com/Online/...performance_ids=`),
which is only on each event page.
