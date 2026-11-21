"""Enrich the people and organizations Artsdata links to ISNI with data from ISNI.

1. Query Artsdata for every ISNI used as a schema:sameAs.
2. Fetch those records from the ISNI SRU API (PICA XML), several per request.
3. Convert each record to schema.org and write output/isni-entities.ttl.

The SRU API limits how many records one IP address can retrieve (about 1,000,
after which it returns empty results for at least a day). When that happens the
script stops asking, and keeps the previous output's data for the ISNIs it
could not fetch, so a blocked run never removes data. ISNIs that are not in the
previous output are fetched first, then the rest in random order.
"""

from __future__ import annotations

import datetime
import logging
import os
import random
import re
import sys
import time
import xml.etree.ElementTree as ET
from collections import Counter
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple
from urllib.parse import unquote, urlparse

import requests
from rdflib import BNode, Graph, Literal, Namespace, URIRef
from rdflib.namespace import RDF, XSD

###############################################################################
# Configuration
###############################################################################

ARTSDATA_ENDPOINT = "https://db.artsdata.ca/repositories/artsdata"
ISNI_SRU_ENDPOINT = "https://isni.oclc.org/sru/DB=1.2/"

OUTPUT_FILE = "output/isni-entities.ttl"

BATCH_SIZE = 25          # ISNIs per SRU request (combined with "or")
REQUEST_DELAY = 1.0      # seconds between SRU requests
HTTP_RETRIES = 3

SPARQL_QUERY = """
SELECT DISTINCT ?isni
WHERE {
    ?entity <http://schema.org/sameAs> ?isni .
    FILTER(STRSTARTS(STR(?isni), "https://isni.org/"))
}
"""

SCHEMA = Namespace("http://schema.org/")
ISNI = Namespace("https://isni.org/isni/")
WD = Namespace("http://www.wikidata.org/entity/")
MUSICBRAINZ_ARTIST = "http://musicbrainz.org/artist/"

# ISNI roles (MARC relator codes, field 032C) -> Wikidata occupations, the
# values Artsdata uses for schema:hasOccupation. Codes too generic to map
# (cre creator, ctb contributor, arr arranger, ...) are left out.
ROLE_OCCUPATIONS = {
    "act": "Q33999",     # actor
    "art": "Q483501",    # artist
    "aut": "Q36180",     # writer
    "chr": "Q2490358",   # choreographer
    "cmp": "Q36834",     # composer
    "cnd": "Q158852",    # conductor
    "dnc": "Q5716684",   # dancer
    "drt": "Q3455803",   # director
    "edt": "Q1607826",   # editor
    "fmp": "Q3282637",   # film producer
    "ill": "Q644687",    # illustrator
    "itr": "Q1278335",   # instrumentalist
    "lyr": "Q822146",    # lyricist
    "mus": "Q639669",    # musician
    "pht": "Q33231",     # photographer
    "prf": "Q713200",    # performing artist
    "sng": "Q177220",    # singer
    "voc": "Q177220",    # singer
}

# Name fields: preferred forms, then alternative ("see from") forms.
PERSON_NAME_TAGS = ("028C", "028A")
PERSON_VARIANT_TAGS = ("028@",)
ORG_NAME_TAGS = ("029C", "029A")
ORG_VARIANT_TAGS = ("029@",)

# 047P links on these hosts are catalogue, social or streaming pages, not the
# entity's own website.
NOT_A_HOMEPAGE = (
    "allmusic.", "amazon.", "apple.com", "bandcamp.", "bandsintown.", "bnf.fr",
    "d-nb.info", "dbpedia.", "deezer.", "discogs.", "facebook.", "genius.",
    "idref.", "imdb.", "instagram.", "isni.", "last.fm", "linkedin.", "loc.gov",
    "musicbrainz.", "muziekweb.", "myspace.", "soundcloud.", "spotify.",
    "tiktok.", "twitter.", "viaf.", "vimeo.", "wikidata.", "wikimedia.",
    "wikipedia.", "worldcat.", "x.com", "youtube.",
)

UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
DATE_RE = re.compile(r"^\d{4}(-\d{2}(-\d{2})?)?$")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")

Fields = List[Tuple[str, List[Tuple[str, str]]]]


class IsniBlocked(Exception):
    """The SRU API found the records but would not return them (quota reached)."""


###############################################################################
# Network operations
###############################################################################

def fetch_isnis_from_artsdata(session: requests.Session) -> List[Dict[str, Any]]:
    """Execute the SPARQL query against Artsdata."""
    logging.info("Fetching ISNIs from Artsdata...")
    try:
        response = session.get(
            ARTSDATA_ENDPOINT,
            params={"query": SPARQL_QUERY},
            headers={
                "Accept": "application/sparql-results+json",
                "User-Agent": "ArtsdataBot/1.0 (https://artsdata.ca/)",
            },
            timeout=120,
        )
        response.raise_for_status()
        return response.json().get("results", {}).get("bindings", [])
    except requests.exceptions.RequestException as exc:
        logging.error("Failed to query Artsdata endpoint: %s", exc)
        return []


def fetch_isni_batch(session: requests.Session, isnis: List[str]) -> Dict[str, Fields]:
    """Fetch several ISNI records in one SRU request.

    Returns {isni: fields} for the ISNIs found; an ISNI that is missing from
    the result does not exist in ISNI. Raises IsniBlocked when the API refuses
    to return records, and requests.RequestException when the API keeps failing.
    """
    # An ISNI can match more than one record (e.g. a duplicate that lists it
    # as merged), so allow more records than ISNIs asked for.
    params = {
        "query": " or ".join(f'pica.isn = "{isni}"' for isni in isnis),
        "version": "1.1",
        "operation": "searchRetrieve",
        "maximumRecords": 2 * len(isnis),
    }
    for attempt in range(1, HTTP_RETRIES + 1):
        try:
            response = session.get(ISNI_SRU_ENDPOINT, params=params, headers={"User-Agent": "ArtsdataBot/1.0"}, timeout=60)
            response.raise_for_status()
            return parse_sru_response(response.content, set(isnis))
        except (requests.exceptions.RequestException, ET.ParseError) as exc:
            if attempt == HTTP_RETRIES:
                raise requests.exceptions.RequestException(str(exc)) from exc
            logging.warning("SRU request failed (%s), retrying in %ds", exc, 10 * attempt)
            time.sleep(10 * attempt)
    return {}


def save_graph(graph: Graph, filename: str) -> None:
    os.makedirs(os.path.dirname(filename), exist_ok=True)
    graph.serialize(filename, format="turtle")
    logging.info("Successfully serialized %d RDF triples to %s", len(graph), filename)


###############################################################################
# Parsing
###############################################################################

def normalise_isni(uri: str) -> Optional[str]:
    """Extract the 16-character ISNI from a URI, ignoring spaces (also %20)."""
    compact = re.sub(r"\s", "", unquote(uri)).upper()
    match = re.search(r"(\d{15}[\dX])/?$", compact)
    return match.group(1) if match else None


def extract_unique_isnis(bindings: List[Dict[str, Any]]) -> Set[str]:
    """Extract a deduplicated set of normalized ISNIs from bindings."""
    isnis = set()
    for row in bindings:
        uri = row.get("isni", {}).get("value")
        isni = normalise_isni(uri) if uri else None
        if isni:
            isnis.add(isni)
        elif uri:
            logging.warning("Ignoring malformed ISNI URI: %s", uri)
    logging.info("Identified %d unique valid ISNIs", len(isnis))
    return isnis


def strip_namespaces(root: ET.Element) -> None:
    for elem in root.iter():
        if "}" in elem.tag:
            elem.tag = elem.tag.split("}", 1)[1]


def record_fields(record: ET.Element) -> Fields:
    """List a PICA record's datafields as (tag, [(code, value), ...])."""
    fields = []
    for datafield in record.iter("datafield"):
        subfields = [(sf.get("code", ""), (sf.text or "").strip()) for sf in datafield.findall("subfield")]
        fields.append((datafield.get("tag", ""), subfields))
    return fields


def parse_sru_response(xml_content: bytes, requested: Set[str]) -> Dict[str, Fields]:
    """Match each record in an SRU response to the requested ISNI(s) it carries.

    A record's own ISNI is in 003E; ISNIs merged into it are in 003F.
    """
    root = ET.fromstring(xml_content)
    strip_namespaces(root)

    records = root.findall(".//recordData")
    number = int(root.findtext(".//numberOfRecords") or "0")
    if not records and number > 0:
        raise IsniBlocked(f"{number} records found but none returned")
    if len(records) < number:
        logging.warning("SRU found %d records but returned %d", number, len(records))

    found: Dict[str, Fields] = {}
    for record in records:
        fields = record_fields(record)
        isnis = {value for tag, sfs in fields if tag in ("003E", "003F") for code, value in sfs if code == "0"}
        for isni in isnis & requested:
            found[isni] = fields
    return found


def values(subfields: List[Tuple[str, str]], code: str) -> List[str]:
    return [value for c, value in subfields if c == code and value]


def first(subfields: List[Tuple[str, str]], code: str) -> Optional[str]:
    found = values(subfields, code)
    return found[0] if found else None


def ppn_to_isni(ppn: str) -> Optional[str]:
    """Convert an ISNI record number (PPN, field 003@ and subfield 9) to its ISNI.

    The ISNI is the PPN without its check character, padded to 15 digits, plus
    the ISO 7064 MOD 11-2 check character.
    """
    base = ppn[:-1]
    if not base.isdigit():
        return None
    base = base.zfill(15)
    total = 0
    for digit in base:
        total = (total + int(digit)) * 2
    check = (12 - total % 11) % 11
    return base + ("X" if check == 10 else str(check))


def person_name(subfields: List[Tuple[str, str]]) -> Optional[str]:
    surname, forename = first(subfields, "a"), first(subfields, "d")
    if surname and forename:
        return f"{forename} {surname}"
    return surname


def org_name(subfields: List[Tuple[str, str]]) -> Optional[str]:
    parts = values(subfields, "a") + values(subfields, "b")
    return ". ".join(parts) if parts else None


def clean_name(name: Optional[str]) -> Optional[str]:
    """Collapse whitespace and trim stray punctuation (e.g. ".. Feist")."""
    if not name:
        return None
    name = re.sub(r"\s+", " ", name).strip(" .,;:-")
    return name or None


def distinct_names(names: List[str], exclude: Optional[str]) -> List[str]:
    """Drop names that differ only in case from the main name or each other,
    preferring a form that isn't all capitals."""
    seen: Dict[str, str] = {}
    for name in names:
        key = name.casefold()
        if key not in seen or (seen[key].isupper() and not name.isupper()):
            seen[key] = name
    if exclude:
        seen.pop(exclude.casefold(), None)
    return sorted(seen.values())


def most_common(items: Iterable[str]) -> Optional[str]:
    """Most frequent item; ties go to the one seen first."""
    counts = Counter(items)
    return counts.most_common(1)[0][0] if counts else None


def pick_date(candidates: List[str]) -> Optional[Literal]:
    """Choose one date from the values the sources give.

    Takes the year most sources agree on, then the most precise value for that
    year. A full date of YYYY-01-01 is treated as a placeholder when another
    source gives only the year.
    """
    valid = [value for value in candidates if DATE_RE.match(value) and valid_date(value)]
    year = most_common(value[:4] for value in valid)
    if not year:
        return None
    same_year = [value for value in valid if value.startswith(year)]
    full = most_common(value for value in same_year if len(value) == 10)
    if full and not (full.endswith("-01-01") and year in same_year):
        return Literal(full, datatype=XSD.date)
    month = most_common(value for value in same_year if len(value) == 7)
    if month:
        return Literal(month, datatype=XSD.gYearMonth)
    return Literal(year, datatype=XSD.gYear)


def valid_date(value: str) -> bool:
    try:
        if len(value) == 10:
            datetime.date.fromisoformat(value)
        elif len(value) == 7:
            datetime.date.fromisoformat(value + "-01")
        return True
    except ValueError:
        return False


def homepage(url: str) -> bool:
    """A bare domain that isn't a catalogue, social or streaming site."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or parsed.path not in ("", "/") or parsed.query:
        return False
    host = parsed.netloc.lower()
    return bool(host) and not any(marker in host for marker in NOT_A_HOMEPAGE)


def parse_isni_record(fields: Fields) -> Dict[str, Any]:
    """Turn a record's PICA fields into the values we publish."""
    type_code = next((first(sfs, "0") for tag, sfs in fields if tag == "002@"), "") or ""
    is_person = len(type_code) >= 2 and type_code[1].lower() == "p"

    # Names: the first preferred form listed (ISNI lists its main form first);
    # every other preferred or variant form is an alternateName. Person name
    # fields on an organization (and the reverse) are names of related
    # entities, so they are ignored.
    name_tags, variant_tags, build = (
        (PERSON_NAME_TAGS, PERSON_VARIANT_TAGS, person_name) if is_person
        else (ORG_NAME_TAGS, ORG_VARIANT_TAGS, org_name)
    )
    preferred = [n for tag in name_tags for t, sfs in fields if t == tag for n in [clean_name(build(sfs))] if n]
    variants = [n for tag in variant_tags for t, sfs in fields if t == tag for n in [clean_name(build(sfs))] if n]
    name = (preferred or variants or [None])[0]
    alternate_names = distinct_names(preferred + variants, exclude=name)

    # Dates (032A): $a start, $b end, $c qualifier. "flourished" and "circa"
    # are not birth or founding dates, so they are skipped.
    dated = [sfs for tag, sfs in fields if tag == "032A" and first(sfs, "c") in (None, "lived")]
    start = pick_date([v for sfs in dated for v in values(sfs, "a")])
    end = pick_date([v for sfs in dated for v in values(sfs, "b")])
    if start is not None and end is not None and str(end)[:4] < str(start)[:4]:
        end = None

    # Country (019A): $a ISO code, sometimes $y region and $z city.
    locations = [sfs for tag, sfs in fields if tag == "019A"]
    country = most_common(
        code.upper() for sfs in locations for code in values(sfs, "a")
        if re.fullmatch(r"[A-Za-z]{2}", code) and code.upper() not in ("XX", "ZZ")
    )
    same_country = [sfs for sfs in locations if (first(sfs, "a") or "").upper() == country]
    region = most_common(v for sfs in same_country for v in values(sfs, "y"))
    locality = most_common(v for sfs in same_country for v in values(sfs, "z"))

    occupations = sorted({
        ROLE_OCCUPATIONS[code] for tag, sfs in fields if tag == "032C"
        for code in values(sfs, "a") if code in ROLE_OCCUPATIONS
    }) if is_person else []

    musicbrainz = {
        mbid.lower() for tag, sfs in fields if tag == "003Z" and first(sfs, "l") == "MUBZ"
        for mbid in values(sfs, "0") if UUID_RE.match(mbid.lower())
    }
    links = [url for tag, sfs in fields if tag == "047P" for url in values(sfs, "u")]
    for url in links:
        match = re.match(r"^https?://(?:www\.)?musicbrainz\.org/artist/([0-9a-f-]{36})", url)
        if match and UUID_RE.match(match.group(1)):
            musicbrainz.add(match.group(1))

    websites: Dict[str, str] = {}
    for url in links:
        if homepage(url):
            websites.setdefault(re.sub(r"^https?://(www\.)?|/$", "", url.lower()), url)

    ipis = sorted({
        ipi for tag, sfs in fields if tag == "006Z" and first(sfs, "l") == "IPI"
        for ipi in values(sfs, "0") if ipi.isdigit()
    })

    # Membership (028Z/029Z $t). Only links that carry the other record's
    # number ($9) can be published; the rest are names only.
    members, member_of = set(), set()
    for tag, sfs in fields:
        relation, ppn = first(sfs, "t"), first(sfs, "9")
        if tag not in ("028Z", "029Z") or not ppn or relation not in ("hasMember", "isMemberOf"):
            continue
        other = ppn_to_isni(ppn)
        if other:
            (members if relation == "hasMember" else member_of).add(other)

    return {
        "type": "Person" if is_person else "Organization",
        "name": name,
        "alternate_names": alternate_names,
        "start": start,
        "end": end,
        "country": country,
        "region": region,
        "locality": locality,
        "occupations": occupations,
        "musicbrainz": sorted(musicbrainz),
        "websites": sorted(websites.values()),
        "ipis": ipis,
        "members": sorted(members),
        "member_of": sorted(member_of),
    }


###############################################################################
# Graph compilation
###############################################################################

def add_record(graph: Graph, isni: str, record: Dict[str, Any]) -> bool:
    """Add one ISNI record to the graph. Returns False if it has no name."""
    if not record["name"]:
        return False
    subject = ISNI[isni]
    is_person = record["type"] == "Person"

    graph.add((subject, RDF.type, SCHEMA.Person if is_person else SCHEMA.Organization))
    graph.add((subject, SCHEMA.name, Literal(record["name"])))
    for alt in record["alternate_names"]:
        graph.add((subject, SCHEMA.alternateName, Literal(alt)))

    if record["start"] is not None:
        graph.add((subject, SCHEMA.birthDate if is_person else SCHEMA.foundingDate, record["start"]))
    if record["end"] is not None:
        graph.add((subject, SCHEMA.deathDate if is_person else SCHEMA.dissolutionDate, record["end"]))

    if record["country"]:
        address = BNode()
        graph.add((subject, SCHEMA.address, address))
        graph.add((address, RDF.type, SCHEMA.PostalAddress))
        graph.add((address, SCHEMA.addressCountry, Literal(record["country"])))
        if record["region"]:
            graph.add((address, SCHEMA.addressRegion, Literal(record["region"])))
        if record["locality"]:
            graph.add((address, SCHEMA.addressLocality, Literal(record["locality"])))

    for qid in record["occupations"]:
        graph.add((subject, SCHEMA.hasOccupation, WD[qid]))
    for mbid in record["musicbrainz"]:
        graph.add((subject, SCHEMA.sameAs, URIRef(MUSICBRAINZ_ARTIST + mbid)))
    for url in record["websites"]:
        graph.add((subject, SCHEMA.url, URIRef(url)))
    for ipi in record["ipis"]:
        identifier = BNode()
        graph.add((subject, SCHEMA.identifier, identifier))
        graph.add((identifier, RDF.type, SCHEMA.PropertyValue))
        graph.add((identifier, SCHEMA.propertyID, Literal("IPI")))
        graph.add((identifier, SCHEMA.value, Literal(ipi)))
    for other in record["members"]:
        graph.add((subject, SCHEMA.member, ISNI[other]))
    for other in record["member_of"]:
        graph.add((subject, SCHEMA.memberOf, ISNI[other]))
    return True


def copy_entity(source: Graph, target: Graph, subject: URIRef) -> None:
    """Copy a subject's triples, and those of the blank nodes it uses."""
    pending = [subject]
    seen = set()
    while pending:
        node = pending.pop()
        if node in seen:
            continue
        seen.add(node)
        for s, p, o in source.triples((node, None, None)):
            target.add((s, p, o))
            if isinstance(o, BNode):
                pending.append(o)


def load_previous(filename: str) -> Graph:
    graph = Graph()
    if os.path.exists(filename):
        graph.parse(filename, format="turtle")
        logging.info("Loaded %d triples from the previous %s", len(graph), filename)
    return graph


def new_graph() -> Graph:
    graph = Graph()
    graph.bind("schema", SCHEMA, override=True, replace=True)
    graph.bind("isni", ISNI)
    graph.bind("wd", WD)
    return graph


###############################################################################
# Execution flow
###############################################################################

def main() -> int:
    previous = load_previous(OUTPUT_FILE)
    previously_output = {str(s)[len(str(ISNI)):] for s in previous.subjects(RDF.type, None) if str(s).startswith(str(ISNI))}

    graph = new_graph()
    fetched: Set[str] = set()
    not_found: Set[str] = set()
    blocked_reason = None

    with requests.Session() as session:
        bindings = fetch_isnis_from_artsdata(session)
        if not bindings:
            logging.error("No data fetched from Artsdata. Exiting.")
            return 1
        isnis = extract_unique_isnis(bindings)

        # New ISNIs first, so they are fetched even if the API quota runs out;
        # the others in random order, so a run that is cut short refreshes a
        # different part of the output each time.
        known = sorted(isnis & previously_output)
        random.shuffle(known)
        ordered = sorted(isnis - previously_output) + known
        logging.info("%d ISNIs are new since the previous output", len(isnis - previously_output))

        for start in range(0, len(ordered), BATCH_SIZE):
            batch = ordered[start:start + BATCH_SIZE]
            logging.info("[%d-%d/%d] Fetching ISNI records", start + 1, start + len(batch), len(ordered))
            found: Dict[str, Fields] = {}
            unresolved: Set[str] = set()  # neither returned nor confirmed missing
            try:
                found = fetch_isni_batch(session, batch)
                # Ask again one by one for any ISNI the batch didn't return,
                # so only ISNIs that really have no record count as not found.
                retry = [isni for isni in batch if isni not in found] if len(batch) > 1 else []
                for position, isni in enumerate(retry):
                    try:
                        time.sleep(REQUEST_DELAY)
                        found.update(fetch_isni_batch(session, [isni]))
                    except (IsniBlocked, requests.exceptions.RequestException):
                        unresolved.update(retry[position:])
                        raise
            except IsniBlocked as exc:
                blocked_reason = str(exc)
                logging.warning("ISNI stopped returning records (%s); keeping previous data for the rest", exc)
            except requests.exceptions.RequestException as exc:
                logging.error("Giving up on ISNIs in batch starting with %s: %s", batch[0], exc)
                if not found:
                    unresolved.update(batch)

            for isni in batch:
                fields = found.get(isni)
                if fields is None:
                    if isni not in unresolved and not (blocked_reason and not found):
                        not_found.add(isni)
                    continue
                try:
                    if not add_record(graph, isni, parse_isni_record(fields)):
                        logging.warning("ISNI %s has no name; skipped", isni)
                    fetched.add(isni)
                except Exception as exc:  # one bad record should not stop the run
                    logging.error("Failed parsing record for %s: %s", isni, exc)
            if blocked_reason:
                break
            time.sleep(REQUEST_DELAY)

    # Keep the previous data for ISNIs that could not be fetched this time.
    carried = 0
    for isni in sorted(isnis - fetched - not_found):
        if isni in previously_output:
            copy_entity(previous, graph, ISNI[isni])
            carried += 1

    logging.info(
        "Fetched %d ISNIs, %d not found in ISNI, %d kept from the previous output, %d missing",
        len(fetched), len(not_found), carried, len(isnis - fetched - not_found) - carried,
    )
    if not_found:
        logging.info("Not found in ISNI: %s", ", ".join(sorted(not_found)))
    if blocked_reason and os.environ.get("GITHUB_ACTIONS"):
        print(f"::warning::ISNI quota reached after {len(fetched)} records ({blocked_reason}); "
              f"kept previous data for {carried} ISNIs.")

    save_graph(graph, OUTPUT_FILE)
    return 0


if __name__ == "__main__":
    sys.exit(main())
