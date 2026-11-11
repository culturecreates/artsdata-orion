---
name: artsdata-automint
description: Turn Artsdata auto-minting on or off for a data feed graph, so events loaded from a Databus artifact are automatically given Artsdata IDs. Use when asked to enable or disable auto-minting (also called "auto-linking" or "automint") for a graph or artifact in Artsdata, typically right after a new artsdata-orion workflow has loaded its first dataset.
---

# Artsdata auto-minting

Auto-minting is a per-graph flag. When it is on, events are minted Artsdata
URIs each time the artifact is loaded into its data feed graph. "Auto-linking"
means the same thing; nebula only has this one toggle.

Nebula is the source of truth for how the flag is stored and updated:
`ArtifactController#toggle_auto_minting` and `#get_automint_status`
(`app/controllers/artifact_controller.rb`), shown as the "Auto-Minting" card on
the artifact page (`app/views/artifact/show.html.erb`). Do not copy its SPARQL
into this skill or write your own update; always go through nebula's code (the
script below) or its web UI, so a change in nebula is picked up automatically.

At the time of writing the flag is one triple in the graph
`http://kg.artsdata.ca/Graph_Ranking`, with predicate
`http://kg.artsdata.ca/ontology/automint` and a boolean value. Treat that as a
description, not a recipe: if it differs from the controller, the controller
is right.

## Graph URI

For a pipeline-action workflow the graph is
`http://kg.artsdata.ca/<account>/<group>/<artifact>`, e.g.
`http://kg.artsdata.ca/culture-creates/artsdata-orion/jazzbistro-ca`.
The group defaults to the repo name; the artifact is the workflow's `artifact`
input. The Databus response in the run log confirms the account and group
(`.../databus/culture-creates/artsdata-orion/<artifact>/...`).

## Steps

1. Check the graph is loaded and see the current flag. Use the Artsdata
   `sparql_query` tool (or https://query.artsdata.ca/query):

   ```sparql
   SELECT ?automint (COUNT(?s) AS ?events) WHERE {
     OPTIONAL { GRAPH <http://kg.artsdata.ca/Graph_Ranking> {
       <GRAPH_URI> <http://kg.artsdata.ca/ontology/automint> ?automint } }
     OPTIONAL { GRAPH <GRAPH_URI> { ?s a <http://schema.org/Event> } }
   } GROUP BY ?automint
   ```

   Zero events means the dataset has not loaded yet (or the URI is wrong).

2. Set the flag. This writes to production Artsdata, so only do it when the
   user asked for it. Either:

   - **Script**: calls nebula's `toggle_auto_minting` action directly, so it
     runs whatever update nebula currently uses, then reads the flag back with
     nebula's `get_automint_status`. It uses the GraphDB credential in nebula's
     encrypted Rails credentials (needs `config/master.key` in the local
     nebula checkout). Pull nebula's `main` first so the code is current.

     ```bash
     zsh -lc 'cd ~/repos/culturecreates/nebula && bin/rails runner \
       ~/repos/culturecreates/artsdata-orion/.agents/skills/artsdata-automint/scripts/set_automint.rb \
       true <GRAPH_URI> [<GRAPH_URI> ...]'
     ```

     Pass `false` instead of `true` to turn it off. Run it through a login
     shell (`zsh -lc`) so rvm picks nebula's Ruby. Never print the credential.

     If the script stops because the action was renamed or changed shape, read
     the controller and update the script's call; do not fall back to a
     hand-written SPARQL update.

   - **Web UI**: sign in at https://kg.artsdata.ca, open the artifact page,
     and press "Turn On" in the Auto-Minting card.

3. The script confirms the result itself. To double-check, or after using the
   web UI, re-run the query from step 1 (adjust it if nebula's storage has
   changed). Tell the user it was done with nebula's stored credential.

## Notes

- Minting happens when an artifact version is loaded. Events loaded before the
  flag was turned on are likely not minted until the next load: re-dispatch the
  workflow (`gh workflow run <file>.yml`) or wait for its schedule.
- Minted Artsdata IDs are permanent, so check the data looks right (names,
  dates, location) before turning it on.
- The public SPARQL endpoint is read-only, which is why the write goes
  through nebula's authenticated update client.
