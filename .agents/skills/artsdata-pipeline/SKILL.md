---
name: artsdata-pipeline
description: Create, test, run and debug GitHub workflows that use culturecreates/artsdata-pipeline-action to crawl a website's JSON-LD and push it to Artsdata. Use when adding a new website/source to artsdata-orion (or an artsdata-planet-* repo), choosing or fixing an entity-identifier selector, running a fetch workflow, or diagnosing a failed "Fetch ... Events" run (no_entity_urls, no_pages_loaded, empty_graph, 403s, databus errors).
---

# Running Artsdata pipeline actions

Each source is one workflow in `.github/workflows/<site>.yml` that calls
`culturecreates/artsdata-pipeline-action@v4`. The action crawls pages, extracts
JSON-LD, commits the result to `output/<file>.jsonld` in the calling repo, and
registers it on the Artsdata Databus as `http://kg.artsdata.ca/<group>/<artifact>`.

Full reference: `~/repos/culturecreates/artsdata-pipeline-action/README.md`
(or https://github.com/culturecreates/artsdata-pipeline-action). Read the source
in `src/` when behaviour is unclear; `src/main.rb` is the entry point and
`src/url_fetcher_service/url_fetcher.rb` handles `entity-identifier`.

## Workflow template (this repo's conventions)

```yaml
name: Fetch <Venue Name> Events

on:
  workflow_dispatch:
  schedule:
    - cron: '17 5 * * 3' # weekly; pick an odd minute/day so runs don't pile up

jobs:
  artsdata-fetch-and-push:
    runs-on: ubuntu-latest
    steps:
      - name: Action setup
        uses: culturecreates/artsdata-pipeline-action@v4
        with:
          mode: "fetch-push"
          artifact: "<domain-tld>"              # e.g. levivier-ca; unreserved chars only
          artifact-file: "output/<domain-tld>-events.jsonld"
          publisher: "${{ secrets.PUBLISHER_URI_GREGORY }}"
          page-url: "https://example.com/events"
          entity-identifier: "a.event-card"     # omit to use the spider crawler
          token: "${{ secrets.GITHUB_TOKEN }}"
          cloudflare-private-key: ${{ secrets.CLOUDFLARE_PRIVATE_KEY }}
```

- Use `artifact-file`; `downloadFile` is a deprecated alias still used in older workflows.
- Always pass `cloudflare-private-key` (signs requests as the registered Artsdata bot).
- Workflows for CAPACOA-loaded sites live in `artsdata-stewards/artsdata-orion`, not here.
- One-off custom runs: the `Custom Fetch and Push` workflow (`caller-custom.yml`) takes
  `page-url`, `entity-identifier`, `artifact`, `publisher` as dispatch inputs.

## Modes

| mode | does |
|---|---|
| `fetch-test` | fetch max 5 entity URLs, save nothing. Use while tuning a selector. |
| `fetch` | crawl and commit `artifact-file`, no Databus push |
| `push` | register an existing `artifact-file`/`downloadUrl` on the Databus |
| `fetch-push` | normal scheduled mode |

## Choosing how to find entity pages

Pick the first that works:

1. **Sitemap** — if the site has an events sitemap (check `robots.txt`, `/sitemap.xml`,
   `/sitemap_index.xml`; WordPress plugins use names like `tribe_events-sitemap.xml`,
   `isl_event-sitemap.xml`), use it as `page-url` with `entity-identifier: "loc"`.
   Most robust: survives theme redesigns.
2. **Listing page + CSS/XPath selector** — `entity-identifier` must select the `<a>`
   elements themselves (the action reads `href`), e.g. `a.ev-avenir`, `div.card > a`.
   Starting with `/` means XPath. Prefer the full listing page over the home page.
3. **Paginated listing** — add `is-paginated: true` (appends page number to `page-url`,
   so it should end with `?page=`), `offset`, or `auto-detect-page-param: true`.
4. **JS-rendered listing** — `fetch-urls-headlessly: true` (and `headless: true` if the
   entity pages also need JavaScript to emit JSON-LD).
5. **URLs already known** — `urls-are-entities: true` with a comma-separated `page-url`.
6. **No identifier** — spider crawler; use when the site is small and has a sitemap.

Other inputs worth knowing: `custom-user-agent` (403s), `max-pages` (default 2500),
`html-extract-config` (add properties via XPath/CSS, incl. `from_property` for linked
pages), `skolemization-exclude`, `custom-sparql` (repo-specific transform), `shacl`.

## Test a selector locally before committing

```bash
ruby .Codex/skills/artsdata-pipeline/scripts/check_selector.rb "<page-url>" "<entity-identifier>" --jsonld
```

It mimics the action's static fetch: prints the match count, the resolved entity
URLs, and (with `--jsonld`) the JSON-LD `@type`s on the first 3 entity pages. On zero
matches it prints a sample of the page's links so you can pick a new selector.
0 matches but the links are visible in a browser → page is JS-rendered (option 4).

Then confirm in CI with `mode: "fetch-test"` on a branch, or just dispatch:

```bash
gh workflow run <file>.yml --ref <branch>
gh run list --workflow <file>.yml --limit 3
gh run view <run-id> --log | grep -E "Fetching entity|Found [0-9]+ elements|Total entities|Max retries|No |Error"
```

Running the action itself locally: in the action repo, `cp sample.config.yml config.yml`,
edit inputs, `bundle exec ruby src/main.rb config.yml`.

## Diagnosing failed runs

```bash
gh run list --status failure --limit 40 --json workflowName,createdAt,databaseId,event
gh run view <id> --log-failed | grep -E "Wrote result.json|Found [0-9]+ elements|Max retries|manifest unknown|Error posting"
```

Logs expire after ~90 days (HTTP 410). Check whether the workflow has already
recovered (latest run per workflow) before fixing anything. `Wrote result.json: failure (<category>)`
gives the classifier's category:

| category | usual cause | fix |
|---|---|---|
| `no_entity_urls` | `Found 0 elements matching ...` — site redesign changed markup, or listing moved | re-run `check_selector.rb`, update `page-url`/`entity-identifier`; prefer a sitemap |
| `no_pages_loaded` | `page-url` 404/403 (e.g. sitemap renamed) | find the new URL from `robots.txt` / sitemap index |
| `empty_graph` | entity pages have no JSON-LD, or need JS | check with `--jsonld`; try `headless: true` |
| `timeout` | headless page never rendered JSON-LD | open the site in a browser; if it is slow or down, re-run later |
| `databus_error` / `databus_exception` | Databus API problem; see `http_status` | re-run later; check api.artsdata.ca |
| `unhandled_exception` + `manifest unknown` | action release published before its Docker image was built | transient; re-run after the image exists |

Repeated `403 Forbidden` / `redirection forbidden` on entity pages (e.g. Ticketpro)
means the site blocks the bot: try `custom-user-agent`, confirm `cloudflare-private-key`
is passed, or switch to a sitemap on the redirected host.

Commit and push workflow changes only when the user asks.
