from __future__ import annotations

import logging
import re
import time
import xml.etree.ElementTree as ET
from typing import Dict, List, Optional, Set

import requests
from rdflib import Graph, Literal, Namespace, URIRef
from rdflib.namespace import RDF, RDFS, OWL, SKOS

###############################################################################
# Configuration
###############################################################################

ARTSDATA_ENDPOINT = "https://db.artsdata.ca/repositories/artsdata"

SPARQL_QUERY = """
PREFIX schema: <http://schema.org/>
PREFIX dbo: <http://dbpedia.org/ontology/>

SELECT DISTINCT ?isni
WHERE {
    ?agent a dbo:Agent ;
           schema:sameAs ?isni .

    FILTER(STRSTARTS(STR(?isni),"https://isni.org/"))
} LIMIT 10
"""

ISNI_ENDPOINT = "https://isni.org/isni/{isni}"

SCHEMA = Namespace("http://schema.org/")
DCTERMS = Namespace("http://purl.org/dc/terms/")
ISNI = Namespace("https://isni.org/isni/")

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s %(message)s",
)

###############################################################################
# Step 1
###############################################################################


def fetch_isnis_from_artsdata() -> List[Dict]:
    """
    Execute the SPARQL query against Artsdata.
    """

    logging.info("Fetching ISNIs from Artsdata...")

    response = requests.get(
        ARTSDATA_ENDPOINT,
        params={
            "query": SPARQL_QUERY,
            "format": "json",
        },
        headers={
            "Accept": "application/sparql-results+json",
            "User-Agent": "ArtsdataDBpediaBot/1.0 (https://artsdata.ca/;)"
        },
        timeout=120,
    )

    response.raise_for_status()

    data =  response.json()
    return data["results"]["bindings"]


###############################################################################
# Step 2
###############################################################################


def normalise_isni(uri: str) -> Optional[str]:
    """
    Extract the ISNI digits.

    https://isni.org/isni/000000012146438X
    ->
    000000012146438X
    """

    match = re.search(r"([0-9X]{16})$", uri)

    if match:
        return match.group(1)

    return None


def extract_unique_isnis(bindings: List[Dict]) -> Set[str]:
    """
    Produce a unique set of ISNIs.
    """

    isnis = set()

    for row in bindings:

        uri = row.get("isni").get("value")

        isni = normalise_isni(uri)

        if isni:
            isnis.add(isni)

    logging.info("Found %d unique ISNIs", len(isnis))

    return isnis


###############################################################################
# Step 3
###############################################################################


def fetch_isni_record(isni: str) -> Optional[str]:
    """
    Download one ISNI record as JSON-LD or RDF/XML.

    Returns the response text.
    """

    url = ISNI_ENDPOINT.format(isni=isni)

    headers = {
        "Accept": "application/ld+json, application/rdf+xml;q=0.9",
        "User-Agent": "ArtsdataDBpediaBot/1.0 (https://artsdata.ca/)"
    }

    try:
        response = requests.get(
            url,
            headers=headers,
            timeout=60,
            allow_redirects=True,
        )

        response.raise_for_status()

        logging.info(
            "Fetched %s (%s)",
            isni,
            response.headers.get("Content-Type"),
        )

        return response.text

    except Exception as exc:
        logging.warning("Failed %s (%s)", isni, exc)
        return None


###############################################################################
# XML Parsing
###############################################################################


def text(element):
    return element.text.strip() if element is not None and element.text else None


def parse_isni_xml(xml: str) -> Dict:
    """
    Parse useful metadata from the ISNI XML.

    This parser intentionally extracts only the most useful fields.
    More fields can easily be added later.
    """

    ns = {
        "srw": "http://www.loc.gov/zing/srw/",
    }

    root = ET.fromstring(xml)

    data = {
        "name": None,
        "description": None,
        "alternate_names": [],
        "occupations": [],
        "countries": [],
    }

    #
    # The SRU response contains MARC XML.
    # Rather than depending on every MARC field,
    # simply iterate through all values.
    #

    for elem in root.iter():

        value = text(elem)

        if not value:
            continue

        tag = elem.tag.lower()

        if data["name"] is None and "name" in tag:
            data["name"] = value

        if "occupation" in tag:
            data["occupations"].append(value)

        if "country" in tag:
            data["countries"].append(value)

        if "description" in tag:
            data["description"] = value

    return data


###############################################################################
# Step 4
###############################################################################


def build_rdf(records: Dict[str, Dict]) -> Graph:
    """
    Transform ISNI records into RDF.
    """

    graph = Graph()

    graph.bind("schema", SCHEMA)
    graph.bind("dcterms", DCTERMS)
    graph.bind("skos", SKOS)

    for isni, record in records.items():

        subject = URIRef(ISNI + isni)

        graph.add((subject, RDF.type, SCHEMA.Person))

        graph.add((subject, OWL.sameAs, subject))

        if record["name"]:
            graph.add(
                (
                    subject,
                    RDFS.label,
                    Literal(record["name"]),
                )
            )

        if record["description"]:
            graph.add(
                (
                    subject,
                    DCTERMS.description,
                    Literal(record["description"]),
                )
            )

        for occupation in record["occupations"]:
            graph.add(
                (
                    subject,
                    SCHEMA.hasOccupation,
                    Literal(occupation),
                )
            )

        for country in record["countries"]:
            graph.add(
                (
                    subject,
                    SCHEMA.homeLocation,
                    Literal(country),
                )
            )

        for alt in record["alternate_names"]:
            graph.add(
                (
                    subject,
                    SKOS.altLabel,
                    Literal(alt),
                )
            )

    return graph


###############################################################################
# Main
###############################################################################


def main():

    bindings = fetch_isnis_from_artsdata()

    isnis = extract_unique_isnis(bindings)

    records = {}

    for index, isni in enumerate(sorted(isnis), start=1):

        logging.info("[%d/%d] %s", index, len(isnis), isni)

        xml = fetch_isni_record(isni)

        if not xml:
            continue

        try:

            records[isni] = parse_isni_xml(xml)

        except Exception as exc:

            logging.warning("%s : %s", isni, exc)

        time.sleep(0.2)

    graph = build_rdf(records)

    graph.serialize("isni.ttl", format="turtle")

    logging.info("Generated %d RDF triples", len(graph))


if __name__ == "__main__":
    main()