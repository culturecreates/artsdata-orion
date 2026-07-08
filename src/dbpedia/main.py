from __future__ import annotations

import os
import re
import time
import urllib.parse
from dataclasses import dataclass
from typing import Dict, List, Optional

import requests
from rdflib import Graph, Literal, Namespace, URIRef, XSD

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
OUTPUT_FILE = "output/dbpedia-entities.ttl"

ARTSDATA_ENDPOINT = "https://db.artsdata.ca/repositories/artsdata"
WIKIDATA_ENDPOINT = "https://query.wikidata.org/sparql"

HEADERS = {
    "Accept": "application/sparql-results+json",
    "User-Agent": "Artsdata DBpedia Enrichment/1.0",
}

SCHEMA = Namespace("http://schema.org/")
RDF = Namespace("http://www.w3.org/1999/02/22-rdf-syntax-ns#")
DBO = Namespace("http://dbpedia.org/ontology/")
DBP = Namespace("http://dbpedia.org/property/")
RDFS = Namespace("http://www.w3.org/2000/01/rdf-schema#")
OWL = Namespace("http://www.w3.org/2002/07/owl#")

QID_PATTERN = re.compile(r"Q\d+$")

SUPPORTED_LANGS = {"en", "fr"}

BATCH_SIZE = 20

ARTSDATA_QUERY = """
PREFIX schema: <http://schema.org/>
PREFIX dbo: <http://dbpedia.org/ontology/>

SELECT DISTINCT ?wikidata
WHERE {
    ?artist a dbo:Agent ;
            schema:sameAs ?wikidata .

    FILTER(
        STRSTARTS(STR(?wikidata),"https://www.wikidata.org/") ||
        STRSTARTS(STR(?wikidata),"http://www.wikidata.org/")
    )
}
"""


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class ArtsdataEntity:
    wikidata_uri: str
    qid: str


# ---------------------------------------------------------------------------
# SPARQL
# ---------------------------------------------------------------------------

def execute_sparql(endpoint: str, query: str, retries=3):
    for attempt in range(retries):
        try:
            response = requests.get(
                endpoint,
                params={
                    "query": query,
                    "format": "json",
                },
                headers=HEADERS,
                timeout=120,
            )

            response.raise_for_status()
            return response.json()

        except requests.RequestException as e:
            print(f"Attempt {attempt + 1} failed: {e}")

            if attempt < retries - 1:
                time.sleep(2 ** attempt)

    return None


# ---------------------------------------------------------------------------
# Artsdata
# ---------------------------------------------------------------------------

def fetch_artsdata_entities() -> List[ArtsdataEntity]:
    print("Fetching Artsdata entities...")

    results = execute_sparql(ARTSDATA_ENDPOINT, ARTSDATA_QUERY)

    entities = []

    for row in results["results"]["bindings"]:

        wikidata_uri = row["wikidata"]["value"]

        match = QID_PATTERN.search(wikidata_uri)

        if not match:
            continue

        entities.append(ArtsdataEntity(wikidata_uri=wikidata_uri, qid=match.group()))

    print(f"Found {len(entities)} entities")

    return entities


# ---------------------------------------------------------------------------
# Wikidata
# ---------------------------------------------------------------------------

def build_wikidata_query(qids: List[str]) -> str:
    values = " ".join(f"wd:{qid}" for qid in qids)

    return f"""
PREFIX schema: <http://schema.org/>
PREFIX wd: <http://www.wikidata.org/entity/>

SELECT ?item ?dbpediaUri
WHERE {{

VALUES ?item {{
{values}
}}

?wikipediaUrl schema:about ?item ;
               schema:isPartOf <https://en.wikipedia.org/> .

BIND(STR(?wikipediaUrl) AS ?wikiStr)
BIND(SUBSTR(?wikiStr,31) AS ?wikiTitle)
BIND(URI(CONCAT("http://dbpedia.org/resource/", ?wikiTitle)) AS ?dbpediaUri)

}}
"""


def resolve_dbpedia_uris(entities: List[ArtsdataEntity]) -> Dict[str, str]:
    print("Resolving DBpedia URIs...")

    mapping = {}

    qids = [e.qid for e in entities]

    for start in range(0, len(qids), BATCH_SIZE):

        batch = qids[start:start + BATCH_SIZE]

        print(f"Processing batch {start}-{start + len(batch)}")

        results = execute_sparql(
            WIKIDATA_ENDPOINT,
            build_wikidata_query(batch),
        )

        if results is None:
            print(f"Skipping batch {start}-{start + len(batch)}")
            continue

        for row in results["results"]["bindings"]:
            qid = row["item"]["value"].split("/")[-1]

            mapping[qid] = row["dbpediaUri"]["value"]

        time.sleep(1)

    print(f"Resolved {len(mapping)} DBpedia resources")

    return mapping


# ---------------------------------------------------------------------------
# DBpedia
# ---------------------------------------------------------------------------

def fetch_dbpedia_json(dbpedia_uri: str) -> Optional[dict]:
    dbpedia_id = dbpedia_uri.split("/")[-1]

    url = f"https://dbpedia.org/data/{dbpedia_id}.json"

    try:
        response = requests.get(url, timeout=60)
        response.raise_for_status()
        return response.json()

    except Exception:
        return None


# ---------------------------------------------------------------------------
# RDF
# ---------------------------------------------------------------------------

def add_uri_values(graph, subject, predicate, values):
    for item in values:
        value = item.get("value")
        if value:
            graph.add((subject, predicate, URIRef(value)))


def add_literal_values(graph, subject, predicate, values, languages=None):
    seen_languages = set()

    for item in values:
        value = item.get("value")
        if not value:
            continue

        lang = item.get("lang")

        # Skip if it's a language we don't care about, or if we've already added it
        if (languages and lang not in languages) or (lang in seen_languages):
            continue

        if lang:
            graph.add((subject, predicate, Literal(value, lang=lang)))
            seen_languages.add(lang)
        else:
            graph.add((subject, predicate, Literal(value)))
            # If you also want to limit non-language/default literals to just one:
            # seen_languages.add(None)


def build_graph(entities: List[ArtsdataEntity], dbpedia_mapping: Dict[str, str], ) -> Graph:
    graph = Graph()

    graph.bind("schema", SCHEMA)

    for entity in entities:

        dbpedia_uri = urllib.parse.unquote(
            dbpedia_mapping.get(entity.qid, "")
        )

        if not dbpedia_uri:
            continue

        data = fetch_dbpedia_json(dbpedia_uri)

        if data is None:
            continue
        subject = URIRef(dbpedia_uri)

        current_item = data.get(dbpedia_uri, {})

        if len(current_item) == 0:
            print(f"DBpedia URI {dbpedia_uri} has no item")
            continue

        types = current_item.get(str(RDF.type), [])

        # type
        if types is not None:
            for entity_type in types:
                type_val = entity_type['value']

                graph.add((subject, RDF.type, URIRef(type_val)))

                if type_val == str(DBO.Person):
                    graph.add((subject, RDF.type, SCHEMA.Person))
                elif type_val == str(DBO.Organisation):
                    graph.add((subject, RDF.type, SCHEMA.Organization))

        # label
        add_literal_values(
            graph,
            subject,
            SCHEMA.name,
            current_item.get(str(RDFS.label), []),
            languages={"en", "fr"},
        )

        # description
        add_literal_values(
            graph,
            subject,
            SCHEMA.disambiguatingDescription,
            current_item.get(str(DBO.description), []),
            languages={"en", "fr"},
        )

        # sameAs
        add_uri_values(
            graph,
            subject,
            SCHEMA.sameAs,
            current_item.get(str(OWL.sameAs), []),
        )

        birth_date = current_item.get(str(DBO.birthDate), [])
        if len(birth_date) > 0:
            graph.add((subject, SCHEMA.birthDate, Literal(birth_date[0].get("value"), datatype=XSD.date)))

        # External Link
        add_uri_values(
            graph,
            subject,
            SCHEMA.url,
            current_item.get(str(DBO.wikiPageExternalLink), []),
        )

        # homepage
        add_uri_values(
            graph,
            subject,
            SCHEMA.url,
            current_item.get(str(DBP.homepage), []),
        )

        # thumbnail
        add_uri_values(
            graph,
            subject,
            SCHEMA.image,
            current_item.get(str(DBO.thumbnail), []),
        )

        # occupation
        for occupation in current_item.get(str(DBP.occupation), []):
            value = occupation.get("value")

            if not value:
                continue

            if occupation.get("type") == "uri":
                graph.add((subject, SCHEMA.occupation, URIRef(value)))
            else:
                graph.add((subject, SCHEMA.occupation, Literal(value)))

    return graph


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def save_graph(graph: Graph, filename: str) -> None:
    os.makedirs(os.path.dirname(filename), exist_ok=True)
    graph.serialize(filename, format="turtle")

    print(f"Generated {filename}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    entities = fetch_artsdata_entities()
    dbpedia_mapping = resolve_dbpedia_uris(entities)
    graph = build_graph(entities, dbpedia_mapping)
    save_graph(graph, OUTPUT_FILE)


if __name__ == "__main__":
    main()
