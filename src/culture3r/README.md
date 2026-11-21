# culture3r

Converts the Culture Trois-Rivières programmation feed to schema.org JSON-LD
for Artsdata. Run by `.github/workflows/culture3r-com-events.yml`.

- Source: `https://www.culture3r.com/wp/wp-admin/admin-ajax.php?action=dates`
  (public, undocumented; it feeds the Vue list on `/programmation/`, built by
  the agency STEREO, so it can change without notice).
- Output: `output/culture3r-com-events.jsonld`
- Graph: `http://kg.artsdata.ca/culture-creates/artsdata-orion-api/culture3r-com`

```bash
pip install -r src/culture3r/requirements.txt
python src/culture3r/main.py                     # live feed
python src/culture3r/main.py --input dates.json  # saved copy
python src/culture3r/main.py --no-descriptions   # skip the event pages
```

Descriptions are not in the feed, so the script also fetches each upcoming
event's page (about 190, half a second apart) and reads the text in
`.c-main-event__description`. If the site changes that markup, the run logs
`No description found on ...` and events go out without a description.

The mapping decisions (skipped rows, event @ids, venues, event types, offers)
are documented at the top of `main.py`. When the site adds a venue, the script
logs `has no Artsdata ID in VENUES`: look the venue up in Artsdata and add it
to `VENUES`. The automatic repair described below usually does this for you.

## Automatic repair

With `--drift-report drift.json`, the script writes a report of problems that
need a code change, and only creates the file when there are some:

- `unmapped_venues`: an event's venue isn't in `VENUES`.
- `unmapped_categories`: a category slug is in neither `EVENT_TYPES` nor
  `IGNORED_CATEGORIES`.
- `events_without_venue`: an event's `lieu` isn't in the feed's `salles`.
- `missing_descriptions`: more than 20% of event pages had no description, so
  `DESCRIPTION_SELECTOR` probably no longer matches.
- `error`: the conversion failed, e.g. the feed changed shape. The run still
  fails. Network errors (site down) are not reported.

The fetch workflow uploads `drift.json` and the feed it read (`dates.json`) as
the `culture3r-drift` artifact. The data is still pushed to Artsdata, except
after an `error`. The artifact starts `.github/workflows/culture3r-heal.yml`,
which runs Claude (`anthropics/claude-code-action`) to update this folder,
check the fix against `dates.json`, and write a summary. The workflow then
opens a PR from a `culture3r-heal/<run id>` branch. Claude can't commit, push
or edit workflows, and the heal workflow skips while a heal PR is still open.
**Check the Artsdata IDs in the PR before merging.**

Setup: add an `ANTHROPIC_API_KEY` repository secret. To test, dispatch
"Heal Culture Trois-Rivières Converter" with the ID of a fetch run that
uploaded `culture3r-drift`.

Performers are always typed schema:Person: neither the feed nor the pages
say whether an artist is a person or a group, so groups and producers
(e.g. "PRODUCTIONS 42E RUE") are typed Person too.

Not used yet: the AudienceView ticket link
(`billets.culture3r.com/Online/...performance_ids=`) is only on each event
page, so offers point to the event page instead.
