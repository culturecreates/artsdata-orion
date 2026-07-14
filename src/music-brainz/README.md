# MusicBrainz Artist Enrichment Pipeline for Artsdata

A production-ready Python pipeline that harvests artist identity references from **Artsdata**, extracts unique **MusicBrainz UUIDs**, dynamically enriches them using the official **MusicBrainz API**, and maps the resolved details into a standardized RDF Turtle (`.ttl`) knowledge graph matching the `schema.org` vocabulary.

This pipeline is optimized to synchronize cross-domain culture registries, normalizing properties across disjoint metadata ecosystems.

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
│       └── music-brainz-org.yml
├── output/
│   └── music-brainz-artists.ttl  # Generated Output RDF Graph
└── src/
    └── musicbrainz-enricher/
        ├── main.py                # Main script pipeline implementation 
        └── requirements.txt       # Script dependencies