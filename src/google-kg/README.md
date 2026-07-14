# Google Knowledge Graph to Artsdata Pipeline

A lightweight, production-ready Python pipeline that harvests entity data from **Artsdata**, links it to **Wikidata** to resolve **Google Knowledge Graph IDs**, extracts expanded entity details in optimized batches from the **Google Knowledge Graph API**, and serializes the resulting graph into a pristine RDF Turtle (`.ttl`) file. 

This pipeline is designed to run automatically via GitHub Actions, publishing updates back to the Artsdata lifecycle engine.

---

## 🚀 Features

* **SPARQL Ingestion:** Fetches distinct entities from the `db.artsdata.ca` endpoint.
* **Efficient Batching:** Resolves Wikidata alignment properties (`P646` for Google KG IDs) and requests the Google KG API in strict chunks of 100 to optimize performance and prevent network bottlenecks.
* **RDF Standardization:** Produces clean, compliant `schema.org` Linked Data serialized into Turtle format.
* **Fault-Tolerant Network Logic:** Gracefully catches non-JSON network failures, logging context instead of raising unhandled exceptions.
* **Secure Credentialing:** Leverages environment variables (`.env`) for local development and GitHub Secrets for CI/CD environments.

---

## 📂 Project Structure

```text
├── .github/
│   └── workflows/
│       └── google-kg.yml   # CI/CD GitHub Action Automation
├── output/
│   └── google-kg-entities     # Output RDF Graph (Generated)
└── src/
    └── google-kg/
        ├── main.py                # Main Python script execution engine
        ├── requirements.txt       # Production dependencies
        └── .env                   # Local secrets storage (Git ignored)