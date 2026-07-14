# ISNI Entity Resolver for Artsdata

A lightweight, production-ready Python pipeline that harvests entity data from **Artsdata**, links it via **ISNI URIs** to query the official **OCLC SRU API**, extracts expanded entity details (names, alternate names, and entity types) from the raw MARC-like XML payload, and serializes the resulting graph into a pristine RDF Turtle (`.ttl`) file.

This pipeline is designed to cross-reference and enrich identity linkages, translating complex traditional library metadata into clean, standardized Schema.org data models.

---

## 🚀 Features

* **SPARQL Ingestion:** Fetches distinct entities containing an ISNI identifier from the `db.artsdata.ca` repository endpoint.
* **Efficient Request Pooling:** Reuses TCP connections via an active `requests.Session()` instance to optimize connection overhead when fetching individual records.
* **Advanced MARC-XML Parsing:** Dynamically unpacks complex OCLC SRU datafields (`028C`, `028@`, `029C`, `029A`, `002@`) into predictable Python structural dictionaries.
* **Polite Scraping Architecture:** Features a configurable time-delay throttling logic (`time.sleep`) between distinct API requests to respect remote rate limits.
* **RDF Standardization:** Produces clean, compliant `schema.org` Linked Data (`schema:Person`, `schema:Organization`, `schema:name`, `schema:alternateName`) serialized into Turtle format.

---

## 📂 Project Structure

```text
├── .github/
│   └── workflows/
│       └── isni-org.yml
├── output/
│   └── isni-entities.ttl     # Output RDF Graph (Generated)
└── src/
    └── isni-resolver/
        ├── main.py            # Main Python script execution engine
        └── requirements.txt   # Production dependencies (requests, rdflib)