"""City -> UK region lookup.

The upstream data only carries a city name, so to answer "sightings per region" we map
each city onto its ONS region (England) or nation (Scotland / Wales / Northern Ireland).
Unknown cities are kept (never dropped) and reported under region "Unknown".
"""
import re

_REGIONS = {
    "London": ["London"],
    "North West": ["Manchester", "Liverpool", "Lancaster", "Carlisle", "Chester", "Preston", "Salford", "Blackpool"],
    "North East": ["Newcastle upon Tyne", "Sunderland", "Durham", "Middlesbrough"],
    "Yorkshire and The Humber": ["Leeds", "Sheffield", "Bradford", "York", "Hull", "Wakefield"],
    "East Midlands": ["Nottingham", "Leicester", "Derby", "Lincoln", "Northampton"],
    "West Midlands": ["Birmingham", "Coventry", "Wolverhampton", "Stoke-on-Trent", "Worcester", "Hereford", "Lichfield"],
    "East of England": ["Norwich", "Cambridge", "Peterborough", "Chelmsford", "Ipswich", "St Albans", "Colchester"],
    "South East": ["Brighton", "Oxford", "Southampton", "Portsmouth", "Canterbury", "Winchester", "Reading", "Milton Keynes", "Guildford"],
    "South West": ["Bristol", "Bath", "Exeter", "Plymouth", "Gloucester", "Salisbury", "Truro"],
    "Scotland": ["Glasgow", "Edinburgh", "Aberdeen", "Dundee", "Inverness", "Stirling", "Perth"],
    "Wales": ["Cardiff", "Swansea", "Newport", "Wrexham"],
    "Northern Ireland": ["Belfast", "Derry", "Lisburn", "Armagh", "Newry"],
}

_ALIASES = {
    "newcastle": "Newcastle upon Tyne",
    "newcastle on tyne": "Newcastle upon Tyne",
    "kingston upon hull": "Hull",
    "londonderry": "Derry",
    "stoke on trent": "Stoke-on-Trent",
    "stoke": "Stoke-on-Trent",
    "st. albans": "St Albans",
    "saint albans": "St Albans",
    "greater london": "London",
}


def _key(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", name.lower()).strip()


CITY_TO_REGION: dict[str, str] = {c: r for r, cities in _REGIONS.items() for c in cities}
_CANON: dict[str, str] = {_key(c): c for c in CITY_TO_REGION}
_CANON.update({_key(a): c for a, c in _ALIASES.items()})


def canonical_city(raw: str) -> str | None:
    """Return the canonical spelling of a known city, or None if we don't recognise it."""
    return _CANON.get(_key(raw))


def region_for(city: str) -> str:
    return CITY_TO_REGION.get(city, "Unknown")
