# MusicBrainz Artist Enrichment Pipeline for Artsdata

A production-ready Python pipeline that harvests artist identity references from **Artsdata**, extracts unique **MusicBrainz UUIDs**, dynamically enriches them using the official **[MusicBrainz API](https://musicbrainz.org/doc/MusicBrainz_API)**, and maps the resolved details into a standardized RDF Turtle (`.ttl`) knowledge graph matching the `schema.org` vocabulary.

This pipeline is designed to run automatically via GitHub Actions, publishing updates back to the Artsdata lifecycle engine.

---

## 🚀 Features

* **SPARQL Ingestion Engine:** Connects to the `db.artsdata.ca` endpoint using the `SPARQLWrapper` interface to isolate distinct `dbo:Agent` records containing explicit MusicBrainz links.
* **Polite Scraping Governance:** Enforces a strict, rate-conscious request throttling delay (`1.1` seconds) between external API invocations to adhere strictly to the MusicBrainz API usage guidelines.
* **Taxonomy Alignment:** Map-transforms internal MusicBrainz structural `type-id` UUIDs directly to precise `schema.org` classes (such as `schema:Person` vs. `schema:MusicGroup`).
* **Semantic Inference:** Automatically maps parent-child relations dynamically (e.g., asserting an entity as a `schema:Organization` whenever it matches a `schema:MusicGroup`).
* **Rich Identity Linking:** Captures auxiliary entity characteristics including formal names, identifiers, gender classes, and related cross-platform identity links like `isni.org` URIs.

---

## 📂 Project Structure

```text
├── .github/
│   └── workflows/
│       └── music-brainz-org.yml    # CI/CD GitHub Action Automation
├── output/
│   └── music-brainz-artists.ttl  # Output RDF Graph (Generated)
└── src/
    └── musicbrainz-enricher/
        ├── main.py                # Main Python script execution engine
        └── requirements.txt       # Script dependencies
```

## Normalized canonical URIs
The script uses **http** as the normalized protocol.

`http://musicbrainz.org/artist/{artist_id}`

This follows and alligns with the Wikidata normalized URIs generated for MusicBrainz using [wdtn:P434](https://query.wikidata.org/#PREFIX%20wdtn%3A%20%3Chttp%3A%2F%2Fwww.wikidata.org%2Fprop%2Fdirect-normalized%2F%3E%0Aselect%20%2a%20where%20%7B%3Fa%20wdtn%3AP434%20%3Fid%7D%0Alimit%20100%0A). See **formatter URI for RDF resource** property in [P434](https://www.wikidata.org/wiki/Property:P434)
