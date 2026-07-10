from __future__ import annotations

import logging
import os
import re
import time
import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional, Set

import requests
from rdflib import Graph, Literal, Namespace, URIRef
from rdflib.namespace import RDF, RDFS

###############################################################################
# Configuration
###############################################################################

ARTSDATA_ENDPOINT = "https://db.artsdata.ca/repositories/artsdata"
ISNI_SRU_ENDPOINT = "https://isni.oclc.org/sru/DB=1.2/"

OUTPUT_FILE = "output/isni-entities.ttl"

SPARQL_QUERY = """
PREFIX schema: <http://schema.org/>
PREFIX dbo: <http://dbpedia.org/ontology/>

SELECT DISTINCT ?isni
WHERE {
    ?agent a dbo:Agent ;
           schema:sameAs ?isni .

    FILTER(STRSTARTS(STR(?isni),"https://isni.org/"))
} LIMIT 50
"""

SCHEMA = Namespace("http://schema.org/")
DCTERMS = Namespace("http://purl.org/dc/terms/")
ISNI = Namespace("https://isni.org/isni/")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")


###############################################################################
# Network Operations
###############################################################################

def fetch_isnis_from_artsdata(session: requests.Session) -> List[Dict[str, Any]]:
    """Execute the SPARQL query against Artsdata."""
    logging.info("Fetching ISNIs from Artsdata...")
    try:
        response = session.get(
            ARTSDATA_ENDPOINT,
            params={"query": SPARQL_QUERY, "format": "json"},
            headers={
                "Accept": "application/sparql-results+json",
                "User-Agent": "ArtsdataDBpediaBot/1.0 (https://artsdata.ca/;)"
            },
            timeout=120,
        )
        response.raise_for_status()
        return response.json().get("results", {}).get("bindings", [])
    except requests.exceptions.RequestException as exc:
        logging.error("Failed to query Artsdata endpoint: %s", exc)
        return []


def fetch_isni_record(session: requests.Session, isni: str) -> Optional[str]:
    """Fetch one ISNI record from the OCLC SRU API using an active session."""
    params = {
        "query": f'pica.isn = "{isni}"',
        "version": "1.1",
        "operation": "searchRetrieve",
        "maximumRecords": 1,
    }
    headers = {"User-Agent": "ArtsdataBot/1.0"}

    try:
        response = session.get(ISNI_SRU_ENDPOINT, params=params, headers=headers, timeout=30)
        response.raise_for_status()
        return response.text
    except requests.exceptions.RequestException as exc:
        logging.warning("Failed to retrieve record for ISNI %s: %s", isni, exc)
        return None


def save_graph(graph: Graph, filename: str) -> None:
    os.makedirs(os.path.dirname(filename), exist_ok=True)
    graph.serialize(filename, format="turtle")
    logging.info("Successfully serialized %d RDF triples to %s", len(graph), filename)


###############################################################################
# Data Parsing & Normalization
###############################################################################

def normalise_isni(uri: str) -> Optional[str]:
    """Extract the 16-character ISNI token from a URI string."""
    match = re.search(r"([0-9X]{16})$", uri)
    return match.group(1) if match else None


def extract_unique_isnis(bindings: List[Dict[str, Any]]) -> Set[str]:
    """Extract a deduplicated set of normalized ISNIs from bindings."""
    isnis = set()
    for row in bindings:
        uri = row.get("isni", {}).get("value")
        if uri:
            isni = normalise_isni(uri)
            if isni:
                isnis.add(isni)
    logging.info("Identified %d unique valid ISNIs", len(isnis))
    return isnis


def parse_isni_xml(xml_content: str) -> Dict[str, Any]:
    """Parse MARC-like XML schemas returned by the OCLC SRU."""
    root = ET.fromstring(xml_content)

    # Strip namespace prefixes dynamically for easier internal element selection
    for elem in root.iter():
        if "}" in elem.tag:
            elem.tag = elem.tag.split("}", 1)[1]

    data = {
        "name": None,
        "alternate_names": [],
        "type": "Organization",
    }

    # Determine Entity Type (Person vs Organization)
    type_field = root.find(".//datafield[@tag='002@']/subfield[@code='0']")
    if type_field is not None and type_field.text:
        code = type_field.text.lower()
        if len(code) >= 2 and code[1] == "p":
            data["type"] = "Person"

    # Process Primary/Preferred Name Tags
    # The first valid name found becomes data["name"], others become alternate_names
    primary_tags = ["028C", "028@", "029C", "029A"]

    for tag in primary_tags:
        df = root.find(f".//datafield[@tag='{tag}']")
        if df is not None:
            a = df.find("./subfield[@code='a']")
            d = df.find("./subfield[@code='d']")

            resolved_name = None
            if d is not None and d.text and a is not None and a.text:
                resolved_name = f"{d.text.strip()} {a.text.strip()}"
            elif a is not None and a.text:
                resolved_name = a.text.strip()

            if resolved_name:
                if data["name"] is None:
                    # Capture only the very first name found
                    data["name"] = resolved_name
                elif resolved_name != data["name"]:
                    # Push the rest of the primary names into alternate_names
                    data["alternate_names"].append(resolved_name)

    # Final cleanup & structural sorting
    data["alternate_names"] = sorted(set(data["alternate_names"]))

    return data


###############################################################################
# Graph Compilation
###############################################################################

def build_rdf(records: Dict[str, Dict[str, Any]]) -> Graph:
    """Transform structured ISNI records into an rdflib Graph object."""
    graph = Graph()
    graph.bind("schema", SCHEMA)

    for isni, record in records.items():
        subject = ISNI[isni]  # Generates URIRef cleanly via __getitem__

        # Assert Primary Label
        if record["name"]:
            # Assert Type
            rdf_type = SCHEMA.Person if record["type"] == "Person" else SCHEMA.Organization
            graph.add((subject, RDF.type, rdf_type))

            graph.add((subject, SCHEMA.name, Literal(record["name"])))
        else:
            continue

        # Assert Alternate Labels
        for alt in record["alternate_names"]:
            graph.add((subject, SCHEMA.alternateName, Literal(alt)))

    return graph


###############################################################################
# Execution Execution Flow
###############################################################################

def main() -> None:
    records = {}

    # Using a requests connection session pool to reuse TCP connections
    with requests.Session() as session:
        bindings = fetch_isnis_from_artsdata(session)
        if not bindings:
            logging.error("No data fetched from Artsdata. Exiting.")
            return

        isnis = extract_unique_isnis(bindings)

        for index, isni in enumerate(sorted(isnis), start=1):
            logging.info("[%d/%d] Processing ISNI: %s", index, len(isnis), isni)

            xml = fetch_isni_record(session, isni)
            if not xml:
                continue

            try:
                records[isni] = parse_isni_xml(xml)
            except Exception as exc:
                logging.error("Failed parsing record XML for %s: %s", isni, exc)

            # Politeness delay between batch records
            time.sleep(0.2)

    # Build and export graph data
    graph = build_rdf(records)
    save_graph(graph, OUTPUT_FILE)


if __name__ == "__main__":
    main()