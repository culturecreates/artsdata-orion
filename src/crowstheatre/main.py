"""Convert the crowstheatre.com schedule to schema.org JSON-LD.

Crow's Theatre (crowstheatre.com) publishes no Event JSON-LD or microdata, but
its schedule page lists every upcoming performance in plain HTML, one month per
page:

    https://www.crowstheatre.com/shows-events/schedule?month=2026-12&p=50

`p` is cumulative (p=2 is the first two pages), so a high `p` returns the whole
month in one request. This script maps each schedule row to a schema:Event and
writes expanded JSON-LD to OUTPUT_FILE, for the artsdata-pipeline-action to
push.

Mapping decisions:
- The months come from the schedule's own month dropdown.
- A row shows only the day and month, so the year comes from the month
  requested. Rows that are on sale or sold out also give the full date in the
  button's aria-label; the two must agree.
- Event @id is <show page URL>#<yyyymmddhhmm>, so a performance keeps its URI
  across runs.
- " @ Soulpepper" and " @ Canadian Stage" are stripped from the show name.
  Those co-presentations are kept, at the partner's venue.
- Venues are linked with schema:sameAs to their Artsdata IDs (VENUES) so they
  reconcile instead of minting new places. The Nada Ristich Studio-Gallery has
  none, and is not in the Crowsnest building (it is at 1210 Dundas St E).
- The organizer is Crow's Theatre (K10-42). Partners, artistic teams and casts
  are only free text on the show pages, so they are not extracted.
- Shows are typed as the Artsdata event type "Theatre Performance", except
  Crow's Cabaret shows, which are mixed: see CABARET_TYPES.
- Sold-out, limited and other on-sale rows get an Offer. "On Sale Soon" rows
  have no ticket link yet, so they get no Offer.
- Description and image come from each show page: the text of the article up
  to the first rule or quote slider, and og:image, falling back to the poster
  in the schedule.
- A show with no rows in the schedule (e.g. one with only a date range) is not
  included, because it has no showtimes.

Usage:
    python src/crowstheatre/main.py                    # fetch the live site
    python src/crowstheatre/main.py --cache pages/     # save pages, and reuse saved ones
    python src/crowstheatre/main.py --allow-drop       # accept a large drop in events
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import time
from dataclasses import dataclass
from datetime import date, datetime
from typing import Dict, List, Optional
from urllib.parse import quote, urljoin, urlsplit, urlunsplit
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup
from rdflib import Graph, Literal, Namespace, URIRef
from rdflib.namespace import RDF, XSD
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

###############################################################################
# Configuration
###############################################################################

SITE = "https://www.crowstheatre.com"
SCHEDULE_URL = f"{SITE}/shows-events/schedule"
OUTPUT_FILE = "output/crowstheatre-com-events.jsonld"
USER_AGENT = "artsdata-crawler"
TZ = ZoneInfo("America/Toronto")
PAGE_DELAY = 0.5  # seconds between requests
ALL_PAGES = 50    # 25 rows per page, so up to 1250 performances in a month

# Fail when upcoming events fall below this share of those in the last output.
MIN_SHARE_OF_PREVIOUS = 0.5
# Fail when more than this share of show pages has no description.
MAX_MISSING_DESCRIPTIONS = 0.5

SCHEMA = Namespace("http://schema.org/")
ARTSDATA = Namespace("http://kg.artsdata.ca/resource/")

ORGANIZER = URIRef(f"{SITE}/#organization")
ORGANIZER_ID = "K10-42"

# Venue name in the schedule -> Artsdata place ID (checked on 2026-11-24) and
# address from the site's show pages.
VENUES = {
    "Guloien Theatre": ("K11-200", "345 Carlaw Ave", "M4M 2T1"),
    "Studio Theatre": ("K11-204", "345 Carlaw Ave", "M4M 2T1"),  # Wikidata Q113856648
    "Nada Ristich Studio-Gallery": (None, "1210 Dundas St E", "M4M 1S3"),
    "Berkeley Street Theatre": ("K11-14", "26 Berkeley Street", "M5A 2W3"),
    "Young Centre for the Performing Arts": ("K2-5867", "50 Tank House Lane", "M5A 3C4"),
}

DEFAULT_TYPE = "TheatrePerformance"
# Crow's Cabaret show slug -> Artsdata event type concept. A cabaret show that
# is not listed gets the generic PerformingArtsEvent, and a warning.
CABARET_TYPES = {
    "comedy-at-crows": "ComedyPerformance",
    "dark-day-cabarets": "MusicPerformance",
    "moneka-arabic-jazz": "MusicPerformance",
}
CABARET_FALLBACK_TYPE = "PerformingArtsEvent"

PARTNER_SUFFIX = re.compile(r"\s+@\s+(Soulpepper|Canadian Stage)$")

# Ticket button text -> has a ticket link, availability. Other availability
# wording ("Selling Fast", "Good Availability") is InStock.
BUY, SOLD_OUT, NOT_ON_SALE = "Buy Tickets", "Sold Out", "On Sale Soon"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")


class SiteChanged(Exception):
    """The site no longer looks as expected; nothing should be written."""


def warn(message: str) -> None:
    """Log a warning, and show it on the GitHub run page when in Actions."""
    logging.warning(message)
    if os.environ.get("GITHUB_ACTIONS"):
        print(f"::warning title=crowstheatre::{message}", flush=True)


@dataclass(frozen=True)
class Row:
    url: str               # show page
    title: str
    venue: str
    start: datetime        # local, with offset
    button: str
    availability: str
    ticket_url: Optional[str]
    poster: Optional[str]

    @property
    def iri(self) -> URIRef:
        return URIRef(f"{self.url}#{self.start:%Y%m%d%H%M}")


@dataclass(frozen=True)
class Show:
    description: Optional[str]
    image: Optional[str]
    is_cabaret: bool


###############################################################################
# Network
###############################################################################

class Pages:
    """Fetches pages politely, optionally saving them to (and reusing) a folder."""

    def __init__(self, cache: Optional[str]):
        self.cache = cache
        self.fetched = 0
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})
        retry = Retry(total=3, backoff_factor=2, status_forcelist=[429, 500, 502, 503, 504])
        self.session.mount("https://", HTTPAdapter(max_retries=retry))

    def get(self, url: str) -> BeautifulSoup:
        path = None
        if self.cache:
            os.makedirs(self.cache, exist_ok=True)
            path = os.path.join(self.cache, re.sub(r"[^A-Za-z0-9]+", "_", url) + ".html")
            if os.path.exists(path):
                with open(path, encoding="utf-8") as f:
                    return BeautifulSoup(f.read(), "html.parser")
        if self.fetched:
            time.sleep(PAGE_DELAY)
        self.fetched += 1
        logging.info("Fetching %s", url)
        response = self.session.get(url, timeout=60)
        response.raise_for_status()
        response.encoding = "utf-8"
        if path:
            with open(path, "w", encoding="utf-8") as f:
                f.write(response.text)
        return BeautifulSoup(response.text, "html.parser")


def clean(value: str) -> str:
    return " ".join(value.replace("\xa0", " ").split())


def absolute(url: str) -> str:
    """Absolute URL with its path percent-encoded (image paths have spaces and quotes)."""
    parts = urlsplit(urljoin(f"{SITE}/", url.strip()))
    return urlunsplit(parts._replace(path=quote(parts.path, safe="/%")))


###############################################################################
# Schedule
###############################################################################

def parse_row(node, month: str) -> Row:
    def select_text(selector: str) -> str:
        found = node.select_one(selector)
        if found is None:
            raise SiteChanged(f"{month}: a schedule row has no {selector}: {clean(node.get_text(' '))[:200]}")
        return clean(found.get_text())

    link = node.select_one(".details .title a[href]")
    button = node.select_one(".action a")
    details = [clean(p.get_text()) for p in node.select(".details > p:not([class])")]
    if link is None or button is None or len(details) != 2:
        raise SiteChanged(f"{month}: unexpected schedule row: {clean(node.get_text(' '))[:200]}")
    venue, clock = details

    year, month_number = map(int, month.split("-"))
    month_name = select_text(".date .mth")
    if month_name != f"{date(year, month_number, 1):%B}":
        raise SiteChanged(f"{month}: a row is dated {month_name}")
    start = datetime.strptime(f"{month}-{select_text('.date .num')} {clock}", "%Y-%m-%d %I:%M%p").replace(tzinfo=TZ)

    label = re.search(r" on (\w{3} \d{1,2}, \d{4}) at (\S+)$", button.get("aria-label", ""))
    if label:
        labelled = datetime.strptime(" ".join(label.groups()), "%b %d, %Y %I:%M%p").replace(tzinfo=TZ)
        if labelled != start:
            raise SiteChanged(f"{month}: row says {start}, its button says {labelled}")

    href = button.get("href", "").strip()
    ticket_url = absolute(href) if href.startswith(("/", "https://", "http://")) else None
    availability = node.select_one(".details .availability")
    poster = node.select_one(".poster img[src]")
    return Row(
        url=absolute(link["href"]).split("?")[0],
        title=clean(link.get_text()),
        venue=venue,
        start=start,
        button=clean(button.get_text()),
        availability=clean(availability.get_text()) if availability else "",
        ticket_url=ticket_url,
        poster=absolute(poster["src"]) if poster else None,
    )


def schedule_rows(page: BeautifulSoup) -> list:
    return page.select(".schedule > .row")


def fetch_schedule(pages: Pages) -> List[Row]:
    # The page has the dropdown more than once (desktop and mobile filters).
    options = pages.get(SCHEDULE_URL).select("select#select-month option[value]")
    months = sorted({option["value"] for option in options})
    if not months or not all(re.fullmatch(r"\d{4}-\d{2}", m) for m in months):
        raise SiteChanged(f"Unexpected months in the schedule's dropdown: {months}")

    rows: List[Row] = []
    for month in months:
        page = pages.get(f"{SCHEDULE_URL}?month={month}&p={ALL_PAGES}")
        nodes = schedule_rows(page)
        more = page.select_one(f'a[href*="month={month}&p="]')
        if more:
            raise SiteChanged(f"{month}: p={ALL_PAGES} does not return the whole month ({more['href']})")
        if not nodes:
            if schedule_rows(pages.get(f"{SCHEDULE_URL}?month={month}")):
                raise SiteChanged(f"{month}: p={ALL_PAGES} is empty but the first page is not")
            warn(f"No performances listed for {month}")
        rows += [parse_row(node, month) for node in nodes]
        logging.info("%s: %s rows", month, len(nodes))
    if not rows:
        raise SiteChanged("No rows in any month of the schedule")
    return rows


###############################################################################
# Show pages
###############################################################################

def html_to_text(nodes: list) -> str:
    """Plain text: one line per <br>, a blank line between blocks."""
    blocks = []
    for node in nodes:
        for br in node.find_all("br"):
            br.replace_with("\n")
        for item in node.find_all(["p", "li", "div"]):
            item.append("\n")
        lines = [clean(line) for line in node.get_text().split("\n")]
        blocks.append("\n".join(line for line in lines if line))
    return "\n\n".join(block for block in blocks if block)


def parse_show(page: BeautifulSoup) -> Show:
    body = []
    article = page.select_one("main article")
    infoblock = article.select_one(".infoblock") if article else None
    if infoblock:
        for node in infoblock.find_next_siblings():
            classes = node.get("class") or []
            if node.name == "hr" or "swiper" in classes:
                break
            if node.name == "select" or "pseudotabs" in classes:
                continue
            body.append(node)
    image = page.select_one('meta[property="og:image"][content]')
    is_cabaret = bool(infoblock) and "CROW'S CABARET" in infoblock.get_text().upper().replace("’", "'")
    return Show(
        description=html_to_text(body) or None,
        image=absolute(image["content"]) if image and image["content"].strip() else None,
        is_cabaret=is_cabaret,
    )


def fetch_shows(pages: Pages, urls: List[str]) -> Dict[str, Show]:
    shows = {}
    for url in urls:
        shows[url] = parse_show(pages.get(url))
        if not shows[url].description:
            warn(f"No description found on {url}")
    missing = [url for url in urls if not shows[url].description]
    if len(missing) > MAX_MISSING_DESCRIPTIONS * len(urls):
        raise SiteChanged(f"{len(missing)} of {len(urls)} show pages have no description")
    return shows


###############################################################################
# Conversion
###############################################################################

def add_organizer(g: Graph) -> None:
    g.add((ORGANIZER, RDF.type, SCHEMA.Organization))
    g.add((ORGANIZER, SCHEMA.name, Literal("Crow's Theatre", lang="en")))
    g.add((ORGANIZER, SCHEMA.url, URIRef(f"{SITE}/")))
    g.add((ORGANIZER, SCHEMA.sameAs, ARTSDATA[ORGANIZER_ID]))


def add_venue(g: Graph, name: str) -> URIRef:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    iri = URIRef(f"{SITE}/about/our-venues#{slug}")
    g.add((iri, RDF.type, SCHEMA.Place))
    g.add((iri, SCHEMA.name, Literal(name, lang="en")))
    if name not in VENUES:
        warn(f"Venue {name} is not in VENUES: add its address and Artsdata ID")
        return iri
    artsdata_id, street, postal_code = VENUES[name]
    address = URIRef(f"{iri}-address")
    g.add((iri, SCHEMA.address, address))
    g.add((address, RDF.type, SCHEMA.PostalAddress))
    g.add((address, SCHEMA.streetAddress, Literal(street)))
    g.add((address, SCHEMA.addressLocality, Literal("Toronto")))
    g.add((address, SCHEMA.addressRegion, Literal("ON")))
    g.add((address, SCHEMA.postalCode, Literal(postal_code)))
    g.add((address, SCHEMA.addressCountry, Literal("CA")))
    if artsdata_id:
        g.add((iri, SCHEMA.sameAs, ARTSDATA[artsdata_id]))
    return iri


def event_type(url: str, show: Show) -> str:
    if not show.is_cabaret:
        return DEFAULT_TYPE
    slug = url.rstrip("/").split("/")[-1]
    if slug not in CABARET_TYPES:
        warn(f"Cabaret show {slug} is not in CABARET_TYPES")
    return CABARET_TYPES.get(slug, CABARET_FALLBACK_TYPE)


def add_offer(g: Graph, row: Row) -> None:
    if row.button == NOT_ON_SALE:
        return
    if row.button == SOLD_OUT:
        availability, url = SCHEMA.SoldOut, row.url
    elif row.button == BUY and row.ticket_url:
        limited = row.availability == "Limited Availability"
        availability, url = (SCHEMA.LimitedAvailability if limited else SCHEMA.InStock), row.ticket_url
    else:
        warn(f"Unknown ticket button '{row.button}' on {row.iri}: no Offer added")
        return
    offer = URIRef(f"{row.iri}-offer")
    g.add((row.iri, SCHEMA.offers, offer))
    g.add((offer, RDF.type, SCHEMA.Offer))
    g.add((offer, SCHEMA.url, URIRef(url)))
    g.add((offer, SCHEMA.availability, availability))


def convert(rows: List[Row], shows: Dict[str, Show]) -> Graph:
    g = Graph()
    g.bind("schema", SCHEMA)
    add_organizer(g)
    venues = {name: add_venue(g, name) for name in sorted({row.venue for row in rows})}
    types = {url: event_type(url, show) for url, show in shows.items()}

    seen: Dict[URIRef, Row] = {}
    for row in rows:
        if row.iri in seen:
            if seen[row.iri].venue != row.venue:
                raise SiteChanged(f"{row.iri} is listed at {seen[row.iri].venue} and {row.venue}")
            warn(f"Skipping duplicate row for {row.iri}")
            continue
        seen[row.iri] = row
        show = shows[row.url]
        g.add((row.iri, RDF.type, SCHEMA.Event))
        g.add((row.iri, SCHEMA.name, Literal(PARTNER_SUFFIX.sub("", row.title), lang="en")))
        g.add((row.iri, SCHEMA.url, URIRef(row.url)))
        g.add((row.iri, SCHEMA.startDate, Literal(row.start.isoformat(), datatype=XSD.dateTime)))
        g.add((row.iri, SCHEMA.location, venues[row.venue]))
        g.add((row.iri, SCHEMA.organizer, ORGANIZER))
        g.add((row.iri, SCHEMA.additionalType, ARTSDATA[types[row.url]]))
        g.add((row.iri, SCHEMA.eventStatus, SCHEMA.EventScheduled))
        g.add((row.iri, SCHEMA.eventAttendanceMode, SCHEMA.OfflineEventAttendanceMode))
        if show.description:
            g.add((row.iri, SCHEMA.description, Literal(show.description, lang="en")))
        image = show.image or row.poster
        if image:
            node = URIRef(f"{image}#ImageObject")
            g.add((row.iri, SCHEMA.image, node))
            g.add((node, RDF.type, SCHEMA.ImageObject))
            g.add((node, SCHEMA.url, URIRef(image)))
        add_offer(g, row)
    logging.info("%s events from %s rows, %s shows", len(seen), len(rows), len(shows))
    return g


def upcoming_in(path: str, now: datetime) -> int:
    """Events in the last output that have not started yet."""
    if not os.path.exists(path):
        return 0
    with open(path, encoding="utf-8") as f:
        nodes = json.load(f)
    starts = [v["@value"] for node in nodes for v in node.get(str(SCHEMA.startDate), [])]
    return sum(datetime.fromisoformat(start) > now for start in starts)


###############################################################################
# Main
###############################################################################

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--output", default=OUTPUT_FILE)
    parser.add_argument("--cache", help="Folder to save fetched pages in; saved pages are reused")
    parser.add_argument("--allow-drop", action="store_true", help="Write even if events drop sharply")
    args = parser.parse_args()

    now = datetime.now(TZ)
    pages = Pages(args.cache)
    rows = [row for row in fetch_schedule(pages) if row.start.date() >= now.date()]
    shows = fetch_shows(pages, sorted({row.url for row in rows}))
    graph = convert(rows, shows)

    count = sum(1 for _ in graph.subjects(RDF.type, SCHEMA.Event))
    previous = upcoming_in(args.output, now)
    if count == 0 or (count < MIN_SHARE_OF_PREVIOUS * previous and not args.allow_drop):
        raise SiteChanged(f"{count} events, but the last output has {previous} still upcoming "
                          "(use --allow-drop if this is right)")
    # rdflib's node order varies from run to run: sort so commits show real changes.
    nodes = json.loads(graph.serialize(format="json-ld", auto_compact=False))
    nodes.sort(key=lambda node: node["@id"])
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(nodes, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")
    logging.info("Wrote %s triples to %s", len(graph), args.output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
