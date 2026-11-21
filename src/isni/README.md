# ISNI entities for Artsdata

`main.py` adds data from [ISNI](https://isni.org) to the people and organizations
Artsdata links to an ISNI. It is run by
[`.github/workflows/isni-org.yml`](../../.github/workflows/isni-org.yml) every week,
writes `output/isni-entities.ttl`, and registers it on the Databus as the
`isni-org` artifact.

## How it works

1. Query `db.artsdata.ca` for every `schema:sameAs` that starts with
   `https://isni.org/`, whatever the entity's type. ISNIs written with spaces
   (`0000%200001%20...`) are normalised.
2. Fetch the records from the ISNI SRU API
   (`https://isni.oclc.org/sru/DB=1.2/`, PICA XML), 25 per request
   (`pica.isn = "..." or pica.isn = "..."`). Each record is matched to the ISNI
   asked for through field `003E` (its ISNI) or `003F` (ISNIs merged into it).
3. Convert each record to schema.org (below) and write Turtle.

### ISNI's quota

ISNI limits how many records one IP address can retrieve: after about 1,000
the API still reports matches (`numberOfRecords`) but returns no records, with
diagnostic `info:srw/diagnostic/1/0`, for a day or more. When that happens the
script stops asking and keeps the previous output's data for every ISNI it
couldn't fetch, so a blocked run never removes data. ISNIs that are new since
the previous output are fetched first, then the rest in random order, so each
run refreshes a different part. In GitHub Actions a blocked run shows a
warning annotation.

ISNIs that ISNI doesn't know, and ISNIs Artsdata no longer links to, are
dropped.

## Mapping

| ISNI field | Output |
|---|---|
| `002@` `$0`, 2nd character `p` | `schema:Person`, otherwise `schema:Organization` |
| People: `028C`/`028A` (`$d $a`); organizations: `029C`/`029A` (`$a. $b`) | `schema:name` is the first one listed; the others are `schema:alternateName` |
| `028@` (people), `029@` (organizations): alternative forms | `schema:alternateName` (case-only duplicates dropped) |
| `032A` `$a`/`$b`, `$c` empty or `lived` | `birthDate`/`deathDate` (people), `foundingDate`/`dissolutionDate` (organizations) |
| `019A` `$a` (ISO country), `$y`, `$z` | `schema:address` → `PostalAddress` `addressCountry`, `addressRegion`, `addressLocality` |
| `032C` `$a` (MARC relator code), people only | `schema:hasOccupation` → Wikidata occupation (`ROLE_OCCUPATIONS` in `main.py`) |
| `003Z` labelled `MUBZ`, and MusicBrainz artist links in `047P` | `schema:sameAs` `http://musicbrainz.org/artist/<id>` |
| `047P` `$u` that is a bare domain, not a catalogue/social/streaming site | `schema:url` |
| `006Z` labelled `IPI` | `schema:identifier` → `PropertyValue` (`propertyID` "IPI") |
| `028Z`/`029Z` `$t hasMember`/`isMemberOf` with a record number in `$9` | `schema:member`/`schema:memberOf` → that record's ISNI |

Dates: when sources disagree, the year most of them give wins, then the most
precise value for that year (`xsd:date`, `xsd:gYearMonth` or `xsd:gYear`).
`YYYY-01-01` counts as a placeholder when another source gives only the year.
`flourished` and `circa` dates are skipped.

Members: most `028Z`/`029Z` links are names only, with no record number, so they
are not published. A record number (PPN) converts to an ISNI by dropping its
check character, padding to 15 digits and adding the ISO 7064 MOD 11-2 check
character.

## Run locally

```sh
pip install -r src/isni/requirements.txt
python src/isni/main.py
```

A full run is close to ISNI's quota, so running it locally can block your own IP
for a day.
