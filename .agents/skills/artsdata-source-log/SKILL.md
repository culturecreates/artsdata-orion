---
name: artsdata-source-log
description: Create or update a source log, the GitHub issue in artsdata-stewards/source-logs that records a data source's graphs, workflows, status, pending tasks and data issues, and link it to its Artsdata graphs. Use when asked to "add a source log", "create a source-log for <site>", update one after a change (auto-minting, ranking, reconciliation), or link a source log to a graph.
---

# Artsdata source logs

A source log is one issue in
[artsdata-stewards/source-logs](https://github.com/artsdata-stewards/source-logs)
for **one source**, covering all its graphs whatever pipeline loads them. The
repo is public and is read by the data stewards (CAPACOA, Culture Creates), who
may not know the pipeline code.

## Template

The issue form is the source of truth for the sections and the allowed
statuses. Read it first, as it can change:

```bash
gh api repos/artsdata-stewards/source-logs/contents/.github/ISSUE_TEMPLATE/source-log.yml -q .content | base64 -d
```

`gh issue create` can't fill in an issue form, so write the body the way the
form renders it: each field's label as a `###` heading, then its value.

## Steps

1. **Look for an existing log.** One source has one log, so search open and
   closed issues by artifact name, domain and organization name, and check
   whether a graph already links to one:

   ```bash
   gh issue list -R artsdata-stewards/source-logs --state all --limit 500 --json number,title,state
   ```

   If there is one, update it instead of creating another.

2. **Find every graph of the source.** Derive the graph URI from the workflow
   (`http://kg.artsdata.ca/<account>/<group>/<artifact>`, see AGENTS.md), and
   look for others: a Footlight graph (`.../culture-creates/footlight/<site>`),
   a Spektrix graph, the sister repo, or an older graph of the same source
   (e.g. left behind when the group changed).

   ```sparql
   SELECT ?g (COUNT(*) AS ?triples) WHERE {
     GRAPH ?g { ?s ?p ?o }
     FILTER(STRSTARTS(STR(?g), "http://kg.artsdata.ca/") && CONTAINS(LCASE(STR(?g)), "<name>"))
   } GROUP BY ?g
   ```

3. **Collect the facts** with the Artsdata `sparql_query` tool. Don't copy them
   from a README or an earlier log:
   - Automint flag, ranking, maintainer and log link are all in
     `http://kg.artsdata.ca/Graph_Ranking`. No automint triple means FALSE.

     ```sparql
     SELECT ?s ?p ?o ?v WHERE { GRAPH <http://kg.artsdata.ca/Graph_Ranking> {
       ?s ?p ?o . FILTER(CONTAINS(STR(?s), "<name>"))
       OPTIONAL { ?o <http://schema.org/ratingValue> ?v } } }
     ```

     A graph is ranked only if **it** has `schema:contentRating`. A
     `<graph>#endorsementRating` node that nothing points to is not a ranking.
   - What is loaded: entities per type, and for events how many are upcoming
     and how many are linked to an Artsdata ID. `artsdata-reload-graph` has the
     query and the direction of the link.
   - Venues and their Artsdata links, with the query in `artsdata-automint`
     (search all graphs, not only the feed graph).
   - The last runs: `gh run list --workflow <file>`, and the warnings in the
     latest log.
   - How the source is read and its known limits: the workflow's comments, the
     SPARQL's comment block or the `src/` README, and recent commits.

4. **Write the log** (next section), save it in the scratchpad, and create it:

   ```bash
   gh issue create -R artsdata-stewards/source-logs --title "<artifact>" --body-file <file>
   ```

   Creating the issue is what the user asked for, so don't ask again. Add
   labels or assignees only if asked; `@` mentions notify people.

5. **Link it to the graphs.** Each graph points to its log with
   `schema:discussionUrl`, which Nebula shows as the "Github Issue" field and
   as the GitHub icon in the feeds list. This writes to production Artsdata,
   so do it only when the user asked for the link, otherwise offer it.
   See "Linking" below.

6. Report the issue URL, the status chosen and why, anything surprising found
   (lost ranking, leftover graph, failing runs), and whether the graphs were
   linked.

## What goes in each section

- **Title:** the artifact name, e.g. `crowstheatre-com`. No "Create ...
  workflow" titles; that is a task, not a source.
- **Maintainer Name:** who maintains the data at the source, not who loads it.
- **Web Page URL:** where the data is published for people, e.g. the events
  page. For an API or a database, its home page; the API goes in the notes.
- **Graph(s) and GitHub Workflow(s):** one row per graph, with the full graph
  URI, a link to the workflow file (a Footlight graph links to
  `https://console.footlight.io/events?seedurl=<site>`), and TRUE or FALSE.
- **Status:** one of the template's options, for the next thing that blocks
  the source. "In production" isn't in the form, but stewards write it by hand
  when nothing is left to do.
- **Tasks:** start from the template. Tick only what was verified. Drop tasks
  that can't apply and say why in the notes: a source without events has
  nothing to auto-mint and no places to reconcile; a reference database
  doesn't need to be notified. Add the source's own tasks, such as choosing
  between two graphs. If a task is partly done, say what is left.
- **Notes:** in this order, skipping what doesn't apply:
  1. Why the source is loaded, and how its graphs relate.
  2. What is loaded, with the date ("As of YYYY-MM-DD"); a table if there are
     several graphs.
  3. How it is read: crawl or API, schedule, link to the transform or `src/`.
  4. Data issues, and which ones the workflow works around.
  5. Venues without an Artsdata link.
  6. What to check before turning on auto-minting.
  7. Suggestions for the website maintainer.

Good examples: [#60](https://github.com/artsdata-stewards/source-logs/issues/60)
(crawl), [#63](https://github.com/artsdata-stewards/source-logs/issues/63) (two
graphs, HTML source), and
[#64](https://github.com/artsdata-stewards/source-logs/issues/64) (reference
database, no events).

Write for the stewards: say what a number means and what needs doing, and link
to code instead of describing it. The repo is public, so leave out private
contact details, emails and credentials. Separate what was checked from what is
assumed.

## Linking

Nebula is the source of truth: `ArtifactController#update_graph_metadata` and
`#get_graph_metadata` (`~/repos/culturecreates/nebula/app/controllers/artifact_controller.rb`).
`update_graph_metadata` **replaces all the graph's metadata** (name,
maintainer, rating and link), so a call with only the link would erase the
ranking. The script reads the current metadata and sends it back with the new
link, through nebula's own code. Pull nebula's `main` first.

```bash
zsh -lc 'cd ~/repos/culturecreates/nebula && bin/rails runner \
  ~/repos/culturecreates/artsdata-orion/.agents/skills/artsdata-source-log/scripts/link_source_log.rb \
  --dry-run <ISSUE_URL> <GRAPH_URI> [<GRAPH_URI> ...]'
```

- Run with `--dry-run` first (it only reads), then without it.
- It refuses to replace a link to a different issue unless given `--replace`,
  and checks afterwards that nothing else changed.
- If a method was renamed or changed shape, read the controller and update the
  script; do not write a SPARQL update by hand.
- Web UI alternative: sign in at https://kg.artsdata.ca, open the artifact,
  fill in "Github Issue" under Graph Metadata and save.

## Updating a log

Read the issue and its comments first (`gh issue view <n> --comments`);
stewards edit the body too, so start from the current body and change only
what is needed. Update the body (`gh issue edit --body-file`) for the current
state: automint column, status, tasks, dated notes. Post a comment for events
in the history or questions to someone. Don't close a log because its tasks
are done unless asked.
