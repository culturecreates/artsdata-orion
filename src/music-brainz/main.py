"""
Fetch artist information from Artsdata GraphDB, enrich it with MusicBrainz data,
and generate an RDF Turtle file.

Steps:
1. Query Artsdata GraphDB for MusicBrainz artist URLs.
2. Extract MusicBrainz artist IDs.
3. Fetch artist details from MusicBrainz API.
4. Convert artist details into RDF.
5. Serialize RDF graph into Turtle.

"""
import logging
import time
from typing import Dict, List, Optional
from urllib.parse import urlparse
import os

import requests
from rdflib import Graph, Literal, Namespace, RDF, URIRef
from rdflib.namespace import OWL
from SPARQLWrapper import JSON, SPARQLWrapper

# ------------------------------------------------------------------------------
# Configuration
# ------------------------------------------------------------------------------

GRAPHDB_ENDPOINT = "https://db.artsdata.ca/repositories/artsdata"

OUTPUT_FILE = "output/music-brainz-artists.ttl"

USER_AGENT = ("ArtsdataBot/1.0")

REQUEST_DELAY_SECONDS = 1.1

# ------------------------------------------------------------------------------
# Namespaces
# ------------------------------------------------------------------------------

SCHEMA = Namespace("http://schema.org/")
DBO = Namespace("http://dbpedia.org/ontology/")
MB = Namespace("http://musicbrainz.org/")
AD = Namespace("https://data.artsdata.ca/resource/")

# ------------------------------------------------------------------------------
# MusicBrainz Artist Type Mapping
# ------------------------------------------------------------------------------

MB_ARTIST_TYPE_MAP = {
    "b6e035f4-3ce9-331c-97df-83397230b0df": SCHEMA.Person,  # Person
    "e431f5f6-b5d2-343d-8b36-72607fffb74b": SCHEMA.MusicGroup,  # Group
    "a0631c1c-95b4-3ec1-ad69-3abe37a003bc": SCHEMA.MusicGroup,  # Orchestra
    "6c2e6d11-fde4-4e4d-bd5d-93e746a76aa6": SCHEMA.MusicGroup,  # Choir
    "c3be71f4-2a63-3174-97ab-7723d23f79a7": SCHEMA.Person,  # Character
    "be1e101b-f5f2-3ec5-b5f7-dc77e4be2f93": SCHEMA.Organization,  # Other
}

GENDER_MAP = {
    "Male": URIRef("http://schema.org/Male"),
    "Female": URIRef("http://schema.org/Female"),
}

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")


# ------------------------------------------------------------------------------
# Main Class
# ------------------------------------------------------------------------------

class MusicBrainzRDFBuilder:

    def __init__(self):
        self.graph = Graph(identifier=URIRef(AD["musicbrainz_graph"]))

        self.graph.bind("schema", SCHEMA)
        self.graph.bind("dbo", DBO)
        self.graph.bind("owl", OWL)
        self.graph.bind("mb", MB)
        self.graph.bind("ad", AD)

    # --------------------------------------------------------------------------
    # SPARQL
    # --------------------------------------------------------------------------

    def fetch_musicbrainz_urls(self) -> List[str]:
        """
        Query Artsdata GraphDB for MusicBrainz artist URLs.
        """

        sparql = SPARQLWrapper(GRAPHDB_ENDPOINT)

        query = """
        PREFIX schema: <http://schema.org/>
        PREFIX dbo: <http://dbpedia.org/ontology/>

        SELECT DISTINCT (?sameAs AS ?music_brand_urls)
        WHERE {
            ?artists a dbo:Agent ;
                     schema:sameAs ?sameAs .

            FILTER(
                STRSTARTS(
                    STR(?sameAs),
                    "https://musicbrainz.org/"
                )
            )
        }
        """

        sparql.setQuery(query)
        sparql.setReturnFormat(JSON)

        results = sparql.query().convert()

        urls = []

        for row in results["results"]["bindings"]:
            urls.append(row["music_brand_urls"]["value"])

        return urls

    # --------------------------------------------------------------------------
    # Utilities
    # --------------------------------------------------------------------------

    @staticmethod
    def extract_artist_id(url: str) -> Optional[str]:
        """
        Extract MusicBrainz UUID from URL.
        """

        parts = urlparse(url).path.strip("/").split("/")

        if len(parts) >= 2:
            return parts[-1]

        return None

    # --------------------------------------------------------------------------
    # MusicBrainz API
    # --------------------------------------------------------------------------

    def fetch_artist(self, artist_id: str) -> Optional[Dict]:

        url = (
            f"https://musicbrainz.org/ws/2/artist/"
            f"{artist_id}?inc=releases&fmt=json"
        )

        headers = {
            "User-Agent": USER_AGENT
        }

        try:

            response = requests.get(
                url,
                headers=headers,
                timeout=30,
            )

            response.raise_for_status()

            time.sleep(REQUEST_DELAY_SECONDS)

            return response.json()

        except Exception as ex:
            logging.error(f"Error retrieving {artist_id}: {ex}")

            return None

    # --------------------------------------------------------------------------
    # RDF
    # --------------------------------------------------------------------------

    def add_artist_to_graph(self, artist: Dict):

        artist_id = artist["id"]

        artist_uri = URIRef(f"http://musicbrainz.org/artist/{artist_id}")

        artist_type = MB_ARTIST_TYPE_MAP.get(artist.get("type-id"),
                                             DBO.Agent)  # fallback if MusicBrainz has an unknown type

        type_id = artist.get("type-id")

        if artist_type is None:
            if type_id and type_id not in self.unknown_artist_types:
                self.unknown_artist_types.add(type_id)
                logging.warning(
                    f"Unknown MusicBrainz type-id: {type_id} "
                    f"(type='{artist.get('type')}', artist='{artist.get('name')}')"
                )

        self.graph.add((artist_uri, RDF.type, artist_type))

        # Check if the type is a MusicGroup, and infer Organization if true
        if artist_type == SCHEMA.MusicGroup:
            self.graph.add((artist_uri, RDF.type, SCHEMA.Organization))

        # Name

        if artist.get("name"):
            self.graph.add((artist_uri, SCHEMA.name, Literal(artist["name"])))

        # Type

        if artist.get("type"):
            self.graph.add((artist_uri, SCHEMA.additionalType, Literal(artist["type"])))

        # Disambiguation

        if artist.get("disambiguation"):
            self.graph.add((artist_uri, SCHEMA.disambiguatingDescription, Literal(artist["disambiguation"])))

        # Gender

        gender = artist.get("gender")

        if gender in GENDER_MAP:
            self.graph.add((artist_uri, SCHEMA.gender, GENDER_MAP[gender]))

        # ISNI

        isnis = artist.get("isnis", [])

        for isni in isnis:
            isni_uri = URIRef(f"https://isni.org/isni/{isni}")
            self.graph.add((artist_uri, SCHEMA.sameAs, URIRef(isni_uri)))

    # --------------------------------------------------------------------------
    # Serialization
    # --------------------------------------------------------------------------

    def save(self, filename: str):
        os.makedirs(os.path.dirname(filename), exist_ok=True)
        self.graph.serialize(destination=filename, format="turtle")

    # --------------------------------------------------------------------------
    # Workflow
    # --------------------------------------------------------------------------

    def run(self):

        urls = self.fetch_musicbrainz_urls()

        logging.info(f"Found {len(urls)} MusicBrainz artists")

        for index, url in enumerate(urls, start=1):

            artist_id = self.extract_artist_id(url)

            if not artist_id:
                continue

            logging.info(f"[{index}/{len(urls)}] Fetching {artist_id}")

            artist = self.fetch_artist(artist_id)

            if artist:
                self.add_artist_to_graph(artist)

        self.save(OUTPUT_FILE)

        logging.info(f"Graph written to {OUTPUT_FILE}")


# ------------------------------------------------------------------------------
# Entry Point
# ------------------------------------------------------------------------------

def main():
    builder = MusicBrainzRDFBuilder()
    builder.run()


if __name__ == "__main__":
    main()
