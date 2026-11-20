"""Convert the culture3r.com programmation feed to schema.org JSON-LD.

Culture Trois-Rivières (culture3r.com) publishes no Event JSON-LD, but its
programmation page is filled from a public JSON feed:

    https://www.culture3r.com/wp/wp-admin/admin-ajax.php?action=dates

The feed has one row per performance (`dates`) plus lookup tables (`salles`,
`categories`, ...). This script maps each row to a schema:Event and writes
expanded JSON-LD to OUTPUT_FILE, for the artsdata-pipeline-action to push.

Mapping decisions:
- Rows with `datestr` set ("Offert à l'année") are year-round exhibitions or
  circuits with a rolling placeholder date, not performances: skipped.
- Rows whose start date has passed are skipped, unless they run over several
  days and have not ended yet.
- Event @id is <event page URL>#<date>T<hhmm> (or #<date> with no time), so a
  performance keeps its URI across runs. The feed sometimes has two rows for
  the same performance; they collapse into one Event.
- The name is the show title, prefixed with the artist when they differ
  ("MÉTHADONE BERTRAND – LES FAUVES").
- Venues come from `salles` and are linked with schema:sameAs to their
  Artsdata IDs (VENUES) so they reconcile instead of minting new places.
- Performers come from `artiste` and are always typed schema:Person; the feed
  doesn't say whether an artist is a person or a group.
- The organizer is Culture Trois-Rivières (K16-40); `presentedby` is the
  sponsor named on the page ("Présenté par Cogeco").
- Categories map to Artsdata event type concepts (EVENT_TYPES).
- `prix` becomes an Offer in CAD; `complet` makes it SoldOut. The ticket link
  (billets.culture3r.com, AudienceView) is not in the feed, so the Offer url is
  the event page.
- The feed has no description, and the page's meta/JSON-LD description is cut
  off at about 300 characters, so the description is read from each event
  page's HTML (`.c-main-event__description`), as plain text with paragraphs
  separated by blank lines. All performances on a page share it. If the page
  can't be fetched, the event goes out without a description.

Usage:
    python src/culture3r/main.py                      # fetch the live feed
    python src/culture3r/main.py --input dates.json   # convert a saved copy
    python src/culture3r/main.py --no-descriptions    # skip the event pages
"""

from __future__ import annotations

import argparse
import html
import json
import logging
import re
import sys
import time
from datetime import date, datetime
from typing import Any, Dict, Iterable, List, Optional
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup
from rdflib import BNode, Graph, Literal, Namespace, URIRef
from rdflib.namespace import RDF, XSD
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

###############################################################################
# Configuration
###############################################################################

FEED_URL = "https://www.culture3r.com/wp/wp-admin/admin-ajax.php?action=dates"
OUTPUT_FILE = "output/culture3r-com-events.jsonld"
USER_AGENT = "ArtsdataOrionBot/1.0 (https://artsdata.ca/; info@culturecreates.com)"
TZ = ZoneInfo("America/Toronto")
PAGE_DELAY = 0.5  # seconds between event page requests
DESCRIPTION_SELECTOR = ".c-main-event__description .o-text"

SCHEMA = Namespace("http://schema.org/")
ARTSDATA = Namespace("http://kg.artsdata.ca/resource/")
SITE = "https://www.culture3r.com"

ORGANIZER = {
    "id": f"{SITE}/#organization",
    "name": "Culture Trois-Rivières",
    "sameAs": ARTSDATA["K16-40"],
    "url": f"{SITE}/",
}

# salles term_id -> Artsdata place ID (checked by name on 2026-11-20).
VENUES = {
    289: "K2-187",     # Salle J.-Antonio-Thompson
    1967: "K5-454",    # Salle Louis-Philippe-Poisson
    1963: "K2-196",    # Salle Anaïs-Allard-Rousseau
    1965: "K16-246",   # Théâtre du Cégep de Trois-Rivières
    101: "K5-694",     # Boréalis
    2191: "K5-453",    # Centre d'exposition Raymond-Lasnier
    5446: "K5-456",    # Espace Pauline-Julien
    231572: "K5-457",  # Bibliothèque Aline-Piché
}

# show_cat slug -> Artsdata event type concept. Unlisted slugs (famille,
# activite-familale, inaugurale, evenement, parcours) add no type.
EVENT_TYPES = {
    "chanson": "Chanson",
    "humour": "ComedyPerformance",
    "theatre": "TheatrePerformance",
    "danse": "DancePerformance",
    "cirque": "CircusPerformance",
    "musique": "MusicPerformance",
    "variete": "VarietyPerformance",
    "projections": "ScreeningEvent",
    "conference": "Conference",
    "atelier": "WorkshopEvent",
    "conte-et-atelier": "StorytellingPerformance",
    "exposition": "ExhibitionEvent",
    "expositions": "ExhibitionEvent",
}

NO_DATE = {"", "1970-01-01", None}

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")


###############################################################################
# Helpers
###############################################################################

def is_true(value: Any) -> bool:
    """The feed mixes true/false, 0/1, "0"/"1" and null for its flags."""
    return value not in (None, False, 0, "0", "", "false")


def text(value: Any) -> str:
    """Decode HTML entities (the feed has e.g. D&rsquo;ÉPELLATION) and trim."""
    return html.unescape(str(value or "")).strip()


def page_url(row: Dict[str, Any]) -> str:
    """Event page URL without the ?rid= performance parameter."""
    return row["url"].split("?")[0]


def start_of(row: Dict[str, Any]) -> Literal:
    """xsd:dateTime with the local offset when there is a time, else xsd:date."""
    if row.get("heure"):
        local = datetime.strptime(f"{row['date']} {row['heure']}", "%Y-%m-%d %H:%M").replace(tzinfo=TZ)
        return Literal(local.isoformat(), datatype=XSD.dateTime)
    return Literal(row["date"], datatype=XSD.date)


def event_iri(row: Dict[str, Any]) -> URIRef:
    suffix = row["date"] + (f"T{row['heure'].replace(':', '')}" if row.get("heure") else "")
    return URIRef(f"{page_url(row)}#{suffix}")


def event_name(row: Dict[str, Any]) -> str:
    title, artist = text(row.get("evenement")), text(row.get("artiste"))
    if not artist or not title or artist.casefold() == title.casefold() or is_true(row.get("hide_show_name")):
        return artist or title
    return f"{artist} – {title}"


def keep(row: Dict[str, Any], today: date) -> bool:
    if row.get("datestr") or not row.get("date") or not row.get("url"):
        return False
    end = row.get("date_fin")
    last_day = end if end not in NO_DATE else row["date"]
    return last_day >= today.isoformat()


###############################################################################
# Network
###############################################################################

def fetch_feed(session: requests.Session) -> Dict[str, Any]:
    logging.info("Fetching %s", FEED_URL)
    response = session.get(FEED_URL, headers={"User-Agent": USER_AGENT, "Accept": "application/json"}, timeout=120)
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict) or "dates" not in data:
        raise ValueError(f"Unexpected feed shape: top-level keys {list(data)[:10] if isinstance(data, dict) else type(data)}")
    return data


def new_session() -> requests.Session:
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    retry = Retry(total=3, backoff_factor=2, status_forcelist=[429, 500, 502, 503, 504])
    session.mount("https://", HTTPAdapter(max_retries=retry))
    return session


def html_to_text(node) -> str:
    """Plain text of an HTML fragment: one line per <br>, a blank line between blocks."""
    for br in node.find_all("br"):
        br.replace_with("\n")
    for block in node.find_all(["p", "div", "li", "ul", "ol", "h1", "h2", "h3", "h4", "h5", "h6"]):
        block.append("\n\n")
    lines = [" ".join(line.replace("\xa0", " ").split()) for line in node.get_text().split("\n")]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def fetch_description(session: requests.Session, url: str) -> Optional[str]:
    response = session.get(url, timeout=60)
    response.raise_for_status()
    node = BeautifulSoup(response.text, "html.parser").select_one(DESCRIPTION_SELECTOR)
    return (html_to_text(node) or None) if node else None


def fetch_descriptions(session: requests.Session, urls: Iterable[str]) -> Dict[str, str]:
    urls = sorted(set(urls))
    logging.info("Fetching descriptions from %s event pages", len(urls))
    descriptions = {}
    for i, url in enumerate(urls):
        if i:
            time.sleep(PAGE_DELAY)
        try:
            description = fetch_description(session, url)
        except requests.RequestException as error:
            logging.warning("Could not fetch %s: %s", url, error)
            continue
        if description:
            descriptions[url] = description
        else:
            logging.warning("No description found on %s", url)
    logging.info("Found descriptions for %s of %s event pages", len(descriptions), len(urls))
    return descriptions


###############################################################################
# Conversion
###############################################################################

def add_venues(g: Graph, salles: List[Dict[str, Any]]) -> Dict[int, URIRef]:
    venues = {}
    for salle in salles:
        term_id = int(salle["term_id"])
        iri = URIRef(f"{SITE}/lieux/#{salle['slug']}")
        g.add((iri, RDF.type, SCHEMA.Place))
        g.add((iri, SCHEMA.name, Literal(text(salle["name"]), lang="fr")))
        address = BNode()
        g.add((iri, SCHEMA.address, address))
        g.add((address, RDF.type, SCHEMA.PostalAddress))
        g.add((address, SCHEMA.addressLocality, Literal("Trois-Rivières")))
        g.add((address, SCHEMA.addressRegion, Literal("QC")))
        g.add((address, SCHEMA.addressCountry, Literal("CA")))
        if term_id in VENUES:
            g.add((iri, SCHEMA.sameAs, ARTSDATA[VENUES[term_id]]))
        else:
            logging.warning("Venue %s (%s) has no Artsdata ID in VENUES", salle["name"], term_id)
        venues[term_id] = iri
    return venues


def add_organizer(g: Graph) -> URIRef:
    iri = URIRef(ORGANIZER["id"])
    g.add((iri, RDF.type, SCHEMA.Organization))
    g.add((iri, SCHEMA.name, Literal(ORGANIZER["name"], lang="fr")))
    g.add((iri, SCHEMA.url, URIRef(ORGANIZER["url"])))
    g.add((iri, SCHEMA.sameAs, ORGANIZER["sameAs"]))
    return iri


def add_event(g: Graph, row: Dict[str, Any], venues: Dict[int, URIRef], organizer: URIRef,
              descriptions: Dict[str, str]) -> None:
    iri = event_iri(row)
    url = page_url(row)
    g.add((iri, RDF.type, SCHEMA.Event))
    g.add((iri, SCHEMA.name, Literal(event_name(row), lang="fr")))
    if url in descriptions:
        g.add((iri, SCHEMA.description, Literal(descriptions[url], lang="fr")))
    g.add((iri, SCHEMA.url, URIRef(url)))
    g.add((iri, SCHEMA.startDate, start_of(row)))
    if row.get("date_fin") not in NO_DATE and row["date_fin"] != row["date"]:
        g.add((iri, SCHEMA.endDate, Literal(row["date_fin"], datatype=XSD.date)))
    if row.get("image"):
        g.add((iri, SCHEMA.image, URIRef(row["image"])))
    g.add((iri, SCHEMA.organizer, organizer))

    venue = venues.get(int(row["lieu"])) if str(row.get("lieu") or "").isdigit() else None
    if venue:
        g.add((iri, SCHEMA.location, venue))
    else:
        logging.warning("No venue for %s (lieu=%s)", iri, row.get("lieu"))

    # Performer: only for real artist records, not exhibitions named after a venue.
    artist = text(row.get("artiste"))
    venue_name = str(g.value(venue, SCHEMA.name)) if venue else ""
    if is_true(row.get("artiste_id")) and artist and artist.casefold() != venue_name.casefold():
        performer = URIRef(f"{SITE}/#artiste-{row['artiste_id']}")
        g.add((iri, SCHEMA.performer, performer))
        g.add((performer, RDF.type, SCHEMA.Person))
        g.add((performer, SCHEMA.name, Literal(artist, lang="fr")))

    if text(row.get("presentedby")):
        sponsor = BNode()
        # Logo variants such as "Hydro-Québec_noir" name the sponsor before the "_".
        g.add((iri, SCHEMA.sponsor, sponsor))
        g.add((sponsor, RDF.type, SCHEMA.Organization))
        g.add((sponsor, SCHEMA.name, Literal(text(row["presentedby"]).split("_")[0])))

    for category in row.get("categories") or []:
        concept = EVENT_TYPES.get(category.get("slug"))
        if concept:
            g.add((iri, SCHEMA.additionalType, ARTSDATA[concept]))

    if is_true(row.get("annule")):
        status = SCHEMA.EventCancelled
    elif is_true(row.get("suspended")):
        status = SCHEMA.EventPostponed
    elif is_true(row.get("report")):
        status = SCHEMA.EventRescheduled
    else:
        status = SCHEMA.EventScheduled
    g.add((iri, SCHEMA.eventStatus, status))
    g.add((iri, SCHEMA.eventAttendanceMode, SCHEMA.OfflineEventAttendanceMode))

    free = any(label.get("slug") == "money" for label in row.get("labels") or [])
    price: Optional[str] = None if row.get("prix") in ("", None) else str(row["prix"])
    if free:
        g.add((iri, SCHEMA.isAccessibleForFree, Literal(True)))
        price = price or "0"
    if price is not None:
        offer = URIRef(f"{iri}-offer")
        g.add((iri, SCHEMA.offers, offer))
        g.add((offer, RDF.type, SCHEMA.Offer))
        g.add((offer, SCHEMA.price, Literal(price, datatype=XSD.decimal)))
        g.add((offer, SCHEMA.priceCurrency, Literal("CAD")))
        g.add((offer, SCHEMA.url, URIRef(url)))
        availability = SCHEMA.SoldOut if is_true(row.get("complet")) else SCHEMA.InStock
        g.add((offer, SCHEMA.availability, availability))


def kept_rows(feed: Dict[str, Any], today: date) -> List[Dict[str, Any]]:
    return [row for row in feed["dates"] if keep(row, today)]


def convert(feed: Dict[str, Any], today: Optional[date] = None,
            descriptions: Optional[Dict[str, str]] = None) -> Graph:
    today = today or datetime.now(TZ).date()
    descriptions = descriptions or {}
    g = Graph()
    g.bind("schema", SCHEMA)
    venues = add_venues(g, feed.get("salles") or [])
    organizer = add_organizer(g)

    rows = kept_rows(feed, today)
    seen = set()
    for row in rows:
        iri = event_iri(row)
        if iri in seen:
            logging.info("Skipping duplicate row %s for %s", row.get("ID"), iri)
            continue
        seen.add(iri)
        add_event(g, row, venues, organizer, descriptions)

    logging.info("%s feed rows, %s kept, %s events", len(feed["dates"]), len(rows), len(seen))
    if not seen:
        raise ValueError("No events produced; the feed may have changed")
    return g


###############################################################################
# Main
###############################################################################

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--input", help="Convert a saved copy of the feed instead of fetching it")
    parser.add_argument("--output", default=OUTPUT_FILE)
    parser.add_argument("--today", help="Override today's date (YYYY-MM-DD), for tests")
    parser.add_argument("--no-descriptions", action="store_true", help="Don't fetch event pages for descriptions")
    args = parser.parse_args()

    today = date.fromisoformat(args.today) if args.today else datetime.now(TZ).date()
    with new_session() as session:
        if args.input:
            with open(args.input, encoding="utf-8") as f:
                feed = json.load(f)
        else:
            feed = fetch_feed(session)
        descriptions = {}
        if not args.no_descriptions:
            descriptions = fetch_descriptions(session, (page_url(row) for row in kept_rows(feed, today)))

    graph = convert(feed, today, descriptions)
    graph.serialize(destination=args.output, format="json-ld", auto_compact=False, indent=2)
    logging.info("Wrote %s triples to %s", len(graph), args.output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
