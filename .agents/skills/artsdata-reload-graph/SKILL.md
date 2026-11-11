---
name: artsdata-reload-graph
description: Reload an existing Databus artifact into its Artsdata data feed graph without re-running the workflow that produced it. Use when asked to "reload the graph", "reload the artifact", or load the latest artifact version into Artsdata, typically right after turning on auto-minting so the events already loaded get minted.
---

# Reload an Artsdata graph from its Databus artifact

Reloading replaces the data in a data feed graph with an artifact version
that is already registered on the Databus. It does not crawl the website or
run a GitHub workflow. Loading is also when auto-minting happens, so reload a
graph after turning auto-minting on (see the `artsdata-automint` skill).

Nebula is the source of truth: `ArtifactController#push_version`
(`app/controllers/artifact_controller.rb`) and `DatabusService#push_version`
(`app/services/databus_service.rb`), shown as the "Reload" button on the
artifact page (`app/views/artifact/show.html.erb`). Do not copy its API call
into this skill or call the Databus API by hand; go through nebula's code (the
script below) or its web UI, so a change in nebula is picked up automatically.

At the time of writing nebula sends a POST to the Databus API
(`push_artifact_version`) with the artifact version's dataset URI and the
publisher `https://github.com/<handle>#this`. The publisher must be on an
Artsdata Databus team. Treat this as a description, not a recipe.

## URIs

- Graph: `http://kg.artsdata.ca/<account>/<group>/<artifact>`, e.g.
  `http://kg.artsdata.ca/culture-creates/artsdata-orion/jazzbistro-ca`.
- Artifact: the same with `/databus` after the host. The script derives it.

If the user says "reload the graph" without naming one, use the graph(s) just
worked on in the conversation; ask only when that is unclear.

## Steps

1. Pull nebula's `main` so the code is current.

2. Optionally preview which version would be loaded (changes nothing):

   ```bash
   zsh -lc 'cd ~/repos/culturecreates/nebula && bin/rails runner \
     ~/repos/culturecreates/artsdata-orion/.agents/skills/artsdata-reload-graph/scripts/reload_graph.rb \
     --dry-run <GRAPH_URI> [<GRAPH_URI> ...]'
   ```

3. Reload. This replaces data in production Artsdata, so only do it when the
   user asked for it. Run the same command without `--dry-run`.

   - Default: reloads the version currently loaded in the graph (what the
     "Reload" button does).
   - `--latest`: loads the newest version on the Databus instead. Use it for
     an artifact that has never been loaded, or when the user asks for the
     latest version.
   - The publisher handle comes from `GITHUB_HANDLE`, else `gh api user`.
   - Run through a login shell (`zsh -lc`) so rvm picks nebula's Ruby.

   Web UI alternative: sign in at https://kg.artsdata.ca, open the artifact
   page, and press "Reload".

4. Report what the script printed. Loading runs in the background on the
   Artsdata side, so a success message means the load was accepted, not that
   it has finished. To check, count the events in the graph after a minute:

   ```sparql
   SELECT (COUNT(?s) AS ?events) WHERE {
     GRAPH <GRAPH_URI> { ?s a <http://schema.org/Event> } }
   ```

If the script stops because a nebula method was renamed or changed shape,
read the controller and update the script's calls; do not fall back to a
hand-written API call.
