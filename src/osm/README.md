# OpenStreetMap Places to Artsdata Pipeline

A continuous integration and automation workflow designed to automatically fetch geographical data from **OpenStreetMap (OSM)** via a localized Python execution engine, compile the parsed results into a standardized Semantic Web Turtle (`.ttl`) graph file, and securely publish updates directly into the **Artsdata** ecosystem.

This pipeline is designed to run automatically via GitHub Actions, publishing updates back to the Artsdata lifecycle engine.

---

## 🚀 Automated Workflow Steps

1. **Environment Initialization:** Spawns a virtual Ubuntu environment, checks out the repository core branch, and initializes the Python runtime.
2. **Dependency Assembly:** Upgrades the internal package manager and provisions environment requirements defined by the engine tracking file.
3. **Data Ingestion Engine:** Executes the localization routine script (`./src/osm/main.py`) which interfaces with OpenStreetMap endpoints to compile spatial nodes into standardized RDF formatting.
4. **Git Version Control Sync:** Evaluates data deltas, tracks the generated graph file (`output/osm-places.ttl`), securely commits updates, and pushes revisions back to the origin repository branch.
5. **Artsdata Engine Broadcast:** Fires a subsequent decoupled job utilizing the `artsdata-pipeline-action` extension to instruct the central Artsdata engine to pull down, parse, and ingest the newly modified public raw artifact.

---

## 📂 Project Structure

To ensure the automated execution runner targets file assets accurately, keep the directory structure organized as follows:

```text
├── .github/
│   └── workflows/
│       └── osm-fetch.yml         # CI/CD GitHub Action Automation
├── output/
│   └── osm-places.ttl            # Output RDF Graph (Generated)
└── src/
    └── osm/
        ├── main.py               # Main Python script execution engine
        └── requirements.txt      # Script dependencies