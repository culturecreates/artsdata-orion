import logging
import time
from typing import List, Dict, Any
from rdflib import Graph, URIRef, Literal, Namespace
from rdflib.namespace import RDF, XSD
import requests
import os
from dotenv import load_dotenv

load_dotenv()
# --- Configuration & Constants ---
ARTSDATA_SPARQL_ENDPOINT = "https://db.artsdata.ca/repositories/artsdata"
WIKIDATA_SPARQL_ENDPOINT = "https://query.wikidata.org/sparql"
GOOGLE_KG_API_URL = "https://kgsearch.googleapis.com/v1/entities:search"

# Replace with your actual Google Knowledge Graph API Key
GOOGLE_KG_API_KEY = os.getenv("GOOGLE_KG_API_KEY")
OUTPUT_TTL_FILE = "output/google-kg-entities"

# Chunks for both Wikidata parsing and Google KG Lookups
BATCH_SIZE = 100

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# Setup Namespaces
SCHEMA = Namespace("http://schema.org/")


def fetch_artsdata_wikidata_uris() -> List[str]:
    """Step 1: Fetch all distinct Wikidata URIs from Artsdata."""
    logging.info("Fetching Wikidata URIs from Artsdata...")

    query = """
    PREFIX schema: <http://schema.org/>
    PREFIX dbo: <http://dbpedia.org/ontology/>
    SELECT DISTINCT ?wikidata_uri WHERE {
        ?place a dbo:Agent ;
               schema:sameAs ?wikidata_uri .
        FILTER(STRSTARTS(STR(?wikidata_uri), "http://www.wikidata.org/") ||
               STRSTARTS(STR(?wikidata_uri), "https://www.wikidata.org/"))
    }
    """

    headers = {
        "Accept": "application/sparql-results+json",
        "User-Agent": "ArtsdataKGExtractor/1.0"
    }

    try:
        response = requests.get(ARTSDATA_SPARQL_ENDPOINT, params={"query": query}, headers=headers, timeout=120)
        response.raise_for_status()
        results = response.json()
        uris = [row["wikidata_uri"]["value"] for row in results["results"]["bindings"]]
        logging.info(f"Found {len(uris)} Wikidata URIs from Artsdata.")
        return uris
    except requests.RequestException as e:
        logging.error(f"Failed to fetch data from Artsdata: {e}")
        return []


def fetch_google_kg_ids_batch(wikidata_uris: List[str]) -> List[str]:
    """Step 2 helper: Query Wikidata for Google KG IDs (P646) for a batch of URIs."""
    qids = []
    for uri in wikidata_uris:
        qid = uri.split("/")[-1]
        if qid.startswith("Q"):
            qids.append(f"wd:{qid}")

    if not qids:
        return []

    qids_str = " ".join(qids)
    query = f"""
    SELECT ?kg_id WHERE {{
      VALUES ?entity {{ {qids_str} }}
      ?entity wdt:P646 ?kg_id .
    }}
    """

    headers = {
        "Accept": "application/sparql-results+json",
        "User-Agent": "ArtsdataKGExtractor/1.0 (contact@example.com)"
    }

    try:
        response = requests.get(WIKIDATA_SPARQL_ENDPOINT, params={"query": query}, headers=headers, timeout=60)
        response.raise_for_status()
        results = response.json()
        return [row["kg_id"]["value"] for row in results["results"]["bindings"]]
    except Exception as e:
        logging.error(f"Error fetching batch from Wikidata: {e}")
        return []


def get_all_google_kg_ids(wikidata_uris: List[str]) -> List[str]:
    """Step 2 & 3: Fetch Google KG IDs in batches and extract unique IDs."""
    logging.info(f"Fetching Google KG IDs from Wikidata in batches of {BATCH_SIZE}...")
    kg_ids = set()

    for i in range(0, len(wikidata_uris), BATCH_SIZE):
        batch = wikidata_uris[i:i + BATCH_SIZE]
        logging.info(f"Querying Wikidata API batch {i // BATCH_SIZE + 1}...")
        batch_ids = fetch_google_kg_ids_batch(batch)
        kg_ids.update(batch_ids)
        time.sleep(0.5)

    logging.info(f"Found {len(kg_ids)} unique Google KG IDs.")
    return list(kg_ids)


def extract_google_kg_data_batch(kg_ids: List[str]) -> List[Dict[str, Any]]:
    """Step 4: Extract specified properties using Google KG API in multi-id batches."""
    # Passing a list to a parameter in requests causes it to duplicate keys (?ids=X&ids=Y)
    params = {
        "ids": kg_ids,
        "key": GOOGLE_KG_API_KEY
    }

    extracted_entities = []
    try:
        response = requests.get(GOOGLE_KG_API_URL, params=params, timeout=60)
        response.raise_for_status()
        data = response.json()

        for item in data.get("itemListElement", []):
            result = item.get("result", {})
            entity_id = result.get("@id", "").replace("kg:", "")

            if not entity_id:
                continue

            extracted = {
                "id": entity_id,
                "types": result.get("@type", []),
                "name": result.get("name"),
                "disambiguatingDescription": result.get("description"),
                "description": result.get("detailedDescription", {}).get("articleBody"),
                "sameAs": result.get("detailedDescription", {}).get("url"),
                "url": result.get("url")
            }
            extracted_entities.append(extracted)

    except Exception as e:
        logging.error(f"Error fetching batch from Google KG API: {e}")

    return extracted_entities


def generate_rdf_graph(entities_data: List[Dict[str, Any]]) -> Graph:
    """Step 6: Generate an RDF graph using Schema.org vocabulary."""
    logging.info("Generating RDF Graph...")
    g = Graph()
    g.bind("schema", SCHEMA)

    for entity in entities_data:
        subject_id = entity["id"]
        subject = URIRef(f"http://g.co/kg{subject_id}")

        for t in entity["types"]:
            g.add((subject, RDF.type, SCHEMA[t]))

        if entity["name"]:
            g.add((subject, SCHEMA.name, Literal(entity["name"])))

        if entity["disambiguatingDescription"]:
            g.add((subject, SCHEMA.disambiguatingDescription, Literal(entity["disambiguatingDescription"])))

        if entity["sameAs"]:
            g.add((subject, SCHEMA.sameAs, URIRef(entity["sameAs"])))

        if entity["description"]:
            g.add((subject, SCHEMA.description, Literal(entity["description"])))

        if entity["url"]:
            g.add((subject, SCHEMA.url, URIRef(entity["url"])))

    return g


def main():
    if not GOOGLE_KG_API_KEY:
        logging.error("Environment variable 'GOOGLE_KG_API_KEY' is missing. Please check your .env file.")
        return

    # Step 1: Fetch Wikidata URIs
    wikidata_uris = fetch_artsdata_wikidata_uris()
    if not wikidata_uris:
        logging.warning("No Wikidata URIs found. Exiting.")
        return

    # Step 2 & 3: Batch fetch & Find unique Google KG IDs
    unique_kg_ids = get_all_google_kg_ids(wikidata_uris)
    if not unique_kg_ids:
        logging.warning("No Google KG IDs resolved. Exiting.")
        return

    # Step 4 & 5: Batch Extract data from Google Knowledge Graph
    logging.info(f"Extracting data from Google KG API in chunks of {BATCH_SIZE}...")
    all_extracted_data = []

    for i in range(0, len(unique_kg_ids), BATCH_SIZE):
        batch = unique_kg_ids[i:i + BATCH_SIZE]
        logging.info(f"Querying Google KG API batch {i // BATCH_SIZE + 1}...")

        batch_data = extract_google_kg_data_batch(batch)
        all_extracted_data.extend(batch_data)
        time.sleep(0.2)  # Short pause between batch requests

    # Step 6: Generate RDF and Serialize to TTL
    graph = generate_rdf_graph(all_extracted_data)

    os.makedirs(os.path.dirname(OUTPUT_TTL_FILE), exist_ok=True)
    graph.serialize(destination=OUTPUT_TTL_FILE, format="turtle")
    logging.info(f"Successfully serialized {len(graph)} triples to {OUTPUT_TTL_FILE}")


if __name__ == "__main__":
    main()
