# DBpedia & Wikidata Entity Resolver for Artsdata

A lightweight, production-ready Python pipeline that harvests entity data from **Artsdata**, links it via **Wikidata** to resolve canonical **DBpedia URIs**, extracts expanded entity details in optimized batches from **DBpedia Data Services**, and serializes the resulting graph into a pristine RDF Turtle (`.ttl`) file. 

This pipeline is designed to run automatically via GitHub Actions, publishing updates back to the Artsdata lifecycle engine.

---

## 🚀 Features

* **SPARQL Ingestion:** Fetches distinct `dbo:Agent` entities from the `db.artsdata.ca` repository endpoint.
* **Efficient Batch Resolution:** Groups Wikidata QIDs into strict chunks of 100 to map them cleanly to DBpedia resource identifiers via the Wikidata SPARQL endpoint, preventing network bottlenecks.
* **High-Performance Enrichment:** Directly queries the DBpedia JSON endpoint instead of executing heavy SPARQL queries, ensuring rapid, lightweight extraction.
* **Bilingual Filtering:** Retains and isolates `en` and `fr` data nodes exclusively for text elements like names and descriptions.
* **Domain Whitelisting:** Strictly enforces strict domain controls over external identity matching (`owl:sameAs`) to support only trusted providers like DBpedia, Wikidata, and MusicBrainz.

---

## 📂 Project Structure

```text
├── .github/
│   └── workflows/
│       └── dbpedia-org.yml   # CI/CD GitHub Action Automation
├── output/
│   └── dbpedia-entities.ttl   # Output RDF Graph (Generated)
└── src/
    └── dbpedia-resolver/
        ├── main.py            # Main Python script execution engine
        └── requirements.txt   # Script dependencies