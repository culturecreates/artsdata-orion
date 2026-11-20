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
- The organizer is Culture Trois-Rivières (K16-40); `presentedby` is the
  sponsor named on the page ("Présenté par Cogeco").
- Categories map to Artsdata event type concepts (EVENT_TYPES).
- `prix` becomes an Offer in CAD; `complet` makes it SoldOut. The ticket link
  (billets.culture3r.com, AudienceView) is not in the feed, so the Offer url is
  the event page.

Usage:
    python src/culture3r/main.py                      # fetch the live feed
    python src/culture3r/main.py --input dates.json   # convert a saved copy
"""

from __future__ import annotations

import argparse
import html
import json
import logging
import sys
from datetime import date, datetime
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

import requests
from rdflib import BNode, Graph, Literal, Namespace, URIRef
from rdflib.namespace import RDF, XSD

###############################################################################
# Configuration
###############################################################################

FEED_URL = "https://www.culture3r.com/wp/wp-admin/admin-ajax.php?action=dates"
OUTPUT_FILE = "output/culture3r-com-events.jsonld"
USER_AGENT = "ArtsdataOrionBot/1.0 (https://artsdata.ca/; info@culturecreates.com)"
TZ = ZoneInfo("America/Toronto")

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


def add_event(g: Graph, row: Dict[str, Any], venues: Dict[int, URIRef], organizer: URIRef) -> None:
    iri = event_iri(row)
    url = page_url(row)
    g.add((iri, RDF.type, SCHEMA.Event))
    g.add((iri, SCHEMA.name, Literal(event_name(row), lang="fr")))
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


def convert(feed: Dict[str, Any], today: Optional[date] = None) -> Graph:
    today = today or datetime.now(TZ).date()
    g = Graph()
    g.bind("schema", SCHEMA)
    venues = add_venues(g, feed.get("salles") or [])
    organizer = add_organizer(g)

    rows = [row for row in feed["dates"] if keep(row, today)]
    seen = set()
    for row in rows:
        iri = event_iri(row)
        if iri in seen:
            logging.info("Skipping duplicate row %s for %s", row.get("ID"), iri)
            continue
        seen.add(iri)
        add_event(g, row, venues, organizer)

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
    args = parser.parse_args()

    if args.input:
        with open(args.input, encoding="utf-8") as f:
            feed = json.load(f)
    else:
        with requests.Session() as session:
            feed = fetch_feed(session)

    today = date.fromisoformat(args.today) if args.today else None
    graph = convert(feed, today)
    graph.serialize(destination=args.output, format="json-ld", auto_compact=False, indent=2)
    logging.info("Wrote %s triples to %s", len(graph), args.output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
