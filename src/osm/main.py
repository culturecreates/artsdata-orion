import logging
import requests
import os
from rdflib import Graph, Literal, Namespace, URIRef, BNode
from rdflib.namespace import RDF, XSD
from SPARQLWrapper import JSON, POST, SPARQLWrapper

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# Namespaces
SCHEMA = Namespace("http://schema.org/")
# Endpoints
ARTSDATA_ENDPOINT = "https://db.artsdata.ca/repositories/artsdata"

WIKIDATA_ENDPOINT = "https://query.wikidata.org/sparql"
OSM_API_URL = "https://api.openstreetmap.org/api/0.6/relation/{}.json"

USER_AGENT = "ArtsdataBot/1.0"

OUTPUT_FILE = "output/osm-places.ttl"

ARTSDATA_SPARQL = query = """
    PREFIX schema: <http://schema.org/>
    SELECT DISTINCT ?place ?wikidata_uri ?postalCode WHERE {
    ?place a schema:Place ;
    schema:sameAs ?wikidata_uri .
    FILTER(STRSTARTS(STR(?wikidata_uri), "http://www.wikidata.org/") ||
        STRSTARTS(STR(?wikidata_uri), "https://www.wikidata.org/"))
    
    #  postal code fetching for verification later
    ?place schema:address ?address .
    ?address schema:postalCode ?postalCode .
}
"""


def query_artsdata():
    """Step 1: Query Artsdata for schema:Place resources with a Wikidata sameAs."""
    logging.info("Querying Artsdata for places with Wikidata links...")
    sparql = SPARQLWrapper(ARTSDATA_ENDPOINT)
    sparql.setQuery(ARTSDATA_SPARQL)
    sparql.setReturnFormat(JSON)
    results = sparql.query().convert()

    places = []
    for result in results["results"]["bindings"]:
        places.append(
            {
                "artsdata_uri": result["place"]["value"],
                "wikidata_uri": result["wikidata_uri"]["value"],
                "address": {
                    "postalCode": result.get("postalCode", {}).get("value", ""),
                },
            }
        )
    logging.info(f"Found {len(places)} candidates from Artsdata.")
    return places


def batch_query_wikidata(wikidata_uris, chunk_size=40):
    """Query Wikidata in manageable chunks using HTTP POST to avoid Broken Pipes."""
    if not wikidata_uris:
        return {}

    logging.info(f"Querying Wikidata for OSM Relation IDs in chunks of {chunk_size}...")

    # Initialize wrapper
    sparql = SPARQLWrapper(WIKIDATA_ENDPOINT)
    sparql.addCustomHttpHeader("User-Agent", USER_AGENT)

    sparql.setMethod(POST)

    wd_to_osm = {}

    # Convert list to unique values just in case
    unique_uris = list(set(wikidata_uris))

    # Split the URIs into smaller chunks
    for i in range(0, len(unique_uris), chunk_size):
        chunk = unique_uris[i:i + chunk_size]
        wd_entities = " ".join([f"<{uri}>" for uri in chunk])

        query = f"""
        PREFIX wdt: <http://www.wikidata.org/prop/direct/>
        SELECT ?wd_entity ?osm_relation_id WHERE {{
            VALUES ?wd_entity {{ {wd_entities} }}
            ?wd_entity wdt:P402 ?osm_relation_id . #P402 OpenStreetMap relation ID
        }}
        """
        sparql.setQuery(query)
        sparql.setReturnFormat(JSON)

        try:
            logging.info(f"Processing chunk {i // chunk_size + 1}...")
            results = sparql.query().convert()

            for result in results["results"]["bindings"]:
                wd_entity = result["wd_entity"]["value"]
                osm_id = result["osm_relation_id"]["value"]
                wd_to_osm[wd_entity] = osm_id

        except Exception as e:
            logging.error(f"Failed to process Wikidata chunk starting at index {i}: {e}")
            # Continue to next chunk instead of crashing the entire script
            continue

    logging.info(f"Successfully mapped {len(wd_to_osm)} Wikidata entities to OSM relations.")
    return wd_to_osm


def fetch_osm_relation(relation_id):
    """Step 4: Retrieve full object from OSM API via Relation ID."""
    url = OSM_API_URL.format(relation_id)
    headers = {"User-Agent": USER_AGENT}
    try:
        response = requests.get(url, headers=headers)
        # FIX: Changed response.status_status to response.status_code
        if response.status_code == 200:
            data = response.json()
            # Find the actual relation element
            for element in data.get("elements", []):
                if (
                        element.get("type") == "relation"
                        and str(element.get("id")) == str(relation_id)
                ):
                    return element
        else:
            logging.warning(
                f"OSM API returned status {response.status_code} for relation {relation_id}"
            )
    except Exception as e:
        logging.error(
            f"Error fetching OSM data for relation {relation_id}: {e}"
        )
    return None


def verify_address(artsdata_addr, osm_tags):
    """Step 5: Simple verification of Artsdata address against OSM address tags."""
    # OSM address tags usually look like addr:postcode, addr:street, etc.
    osm_postcode = osm_tags.get("addr:postcode", "").strip().lower()
    ad_postcode = artsdata_addr.get("postalCode", "").strip().lower()

    # Normalize spacing for basic comparison (e.g., Canadian postal codes "H2W 1Y4" vs "H2W1Y4")
    if (ad_postcode.replace(" ", "") == osm_postcode.replace(" ", "")):
        return True
    else:
        return False


def save_graph(graph: Graph, filename: str) -> None:
    os.makedirs(os.path.dirname(filename), exist_ok=True)
    graph.serialize(filename, format="turtle")
    logging.info("Successfully serialized %d RDF triples to %s", len(graph), filename)


def main():
    # 1. Fetch from Artsdata
    artsdata_places = query_artsdata()
    if not artsdata_places:
        logging.info("No records found to process.")
        return

    wd_uris = [p["wikidata_uri"] for p in artsdata_places]

    # 2 & 3. Filter via Wikidata for OSM relation link
    wd_to_osm_map = batch_query_wikidata(wd_uris)

    # Initialize Output Graph
    graph = Graph()
    # Explicitly bind "schema" to match your expected output prefix
    graph.bind("schema", SCHEMA)

    # Process entities
    for place in artsdata_places:
        wd_uri = place["wikidata_uri"]
        if wd_uri not in wd_to_osm_map:
            continue

        osm_id = wd_to_osm_map[wd_uri]

        # 4. Fetch OSM Details
        osm_element = fetch_osm_relation(osm_id)
        if not osm_element:
            continue

        tags = osm_element.get("tags", {})

        # 5. Verify Artsdata Postal Code against OSM Postal Code
        if not verify_address(place["address"], tags):
            logging.info(f"Postal Code verification failed for {place['artsdata_uri']} (osm_id: {osm_id}). Skipping.")
            continue

        # 6. Generate RDF (Using OSM Relation as the Primary Subject)
        osm_uri = URIRef(f"https://www.openstreetmap.org/relation/{osm_id}")

        # Define schema:Place type
        graph.add((osm_uri, RDF.type, SCHEMA.Place))

        # schema:name from OSM
        name = tags.get("name") or tags.get("official_name")
        if name:
            graph.add((osm_uri, SCHEMA.name, Literal(name)))

        # schema:sameAs -> Wikidata URI
        graph.add((osm_uri, SCHEMA.sameAs, URIRef(wd_uri)))

        # schema:url -> OSM website tag
        website = tags.get("website") or tags.get("url")
        if website:
            graph.add((osm_uri, SCHEMA.url, Literal(website)))

        # schema:disambiguatingDescription (Optional description tag from OSM)
        description = tags.get("description") or tags.get("note")
        if description:
            graph.add((osm_uri, SCHEMA.disambiguatingDescription, Literal(description)))

        # schema:address -> Minted from OSM URI subpath
        if tags.get("addr:street") or tags.get("addr:postcode") or tags.get("addr:city"):
            address_uri = URIRef(f"https://www.openstreetmap.org/relation/{osm_id}/address")
            graph.add((osm_uri, SCHEMA.address, address_uri))
            graph.add((address_uri, RDF.type, SCHEMA.PostalAddress))

            if tags.get("addr:city"):
                graph.add((address_uri, SCHEMA.addressLocality, Literal(tags.get("addr:city"))))

            # Map province/state to Region
            region = tags.get("addr:province")
            if region:
                graph.add((address_uri, SCHEMA.addressRegion, Literal(region)))

            if tags.get("addr:postcode"):
                graph.add((address_uri, SCHEMA.postalCode, Literal(tags.get("addr:postcode"))))

            if tags.get("addr:street"):
                # Combine housenumber and street name if both exist
                housenumber = tags.get("addr:housenumber", "").strip()
                street_name = tags.get("addr:street", "").strip()
                street_full = f"{housenumber} {street_name}".strip()
                graph.add((address_uri, SCHEMA.streetAddress, Literal(street_full)))

    # Output final Turtle format
    save_graph(graph, OUTPUT_FILE)


if __name__ == "__main__":
    main()
