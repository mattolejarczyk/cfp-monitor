"""A checked lookup from a state or province named in a sentence to the country it belongs to (ACT-23, failure point C3).

    country_from_region("Las Vegas, NV")            -> ("United States", "NV (Nevada)")
    country_from_region("Toronto, Ontario")         -> ("Canada", "Ontario")
    country_from_region("Paris, France") / "Georgia" -> None

WHY. A page often states the place only as 'Las Vegas, NV' or 'Boston, MA | May 10-12th, 2027'. The reader returns country 'United States' with that sentence as its quote, and the
quote-check rule 'the value must be inside the quote' refused it, so the country stayed blank (CES 2027, ODSC East). A person reads 'NV' and knows. Code can do the same, but only from a CHECKED table:
United States (50 states and DC), Canada (10 provinces, 3 territories) and Australia (6 states, 2 territories). Nothing else is guessed.
RULES (precision first; a wrong country is worse than a blank):
  - a full name matches as a whole word, any case, EXCEPT names that are also a country, a city or a person far more often than the region: Georgia, Washington, New York (their two-letter codes
    still work in 'Atlanta, GA'; 'Victoria' alone is not in the table because it is also a Canadian city);
  - a two-letter code matches only as an UPPERCASE token right after a comma and a capitalised word ('Austin, TX 78701', 'Boston, MA | ...'), and must be followed by the end, punctuation, a digit or a capital;
  - a code shared by two countries (WA: Washington / Western Australia, NT: Northwest Territories / Northern Territory) makes the whole sentence ambiguous: the answer is None; the other
    Australian codes are not in the table at all;
  - if the quote names regions of TWO different countries the answer is None (no guess)."""
from __future__ import annotations

import re

US = {"AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas", "CA": "California", "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware", "FL": "Florida", "GA": "Georgia",
      "HI": "Hawaii", "ID": "Idaho", "IL": "Illinois", "IN": "Indiana", "IA": "Iowa", "KS": "Kansas", "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland",
      "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota", "MS": "Mississippi", "MO": "Missouri", "MT": "Montana", "NE": "Nebraska", "NV": "Nevada", "NH": "New Hampshire",
      "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York", "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma", "OR": "Oregon", "PA": "Pennsylvania",
      "RI": "Rhode Island", "SC": "South Carolina", "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas", "UT": "Utah", "VT": "Vermont", "VA": "Virginia", "WA": "Washington",
      "WV": "West Virginia", "WI": "Wisconsin", "WY": "Wyoming", "DC": "District of Columbia"}
CANADA = {"AB": "Alberta", "BC": "British Columbia", "MB": "Manitoba", "NB": "New Brunswick", "NL": "Newfoundland and Labrador", "NS": "Nova Scotia", "NT": "Northwest Territories",
          "NU": "Nunavut", "ON": "Ontario", "PE": "Prince Edward Island", "QC": "Quebec", "SK": "Saskatchewan", "YT": "Yukon"}
AUSTRALIA = ["New South Wales", "Queensland", "Western Australia", "South Australia", "Tasmania", "Australian Capital Territory", "Northern Territory"]    # 'Victoria' alone is also a Canadian and a Seychelles city

# names that must not be read as a region: a country, or too ambiguous (a US state named 'Georgia' is also a country; 'Washington' alone is usually the city or the person)
_NAME_SKIP = {"georgia", "washington", "new york"}
_SHARED_CODES = {"WA", "NT"}        # two countries share them: never used
_WORDLIKE = {"IN", "OR", "ME", "OK", "HI", "ID", "LA", "DE", "OH", "ON", "AS", "AT", "IS", "IT", "NO"}   # codes that are also English words: not read before a lowercase word
_COUNTRY_NAMES = {"United States": "United States", "Canada": "Canada", "Australia": "Australia"}
COUNTRY_ALIASES = {"United States": {"united states", "united states of america", "usa", "us", "u s a", "u s", "america"}, "Canada": {"canada"}, "Australia": {"australia"}}


def _names() -> list[tuple[str, str, str]]:
    """(lowercase name, country, label) for every region name usable on its own."""
    out = []
    for name in US.values():
        if name.lower() not in _NAME_SKIP:
            out.append((name.lower(), "United States", name))
    for name in CANADA.values():
        out.append((name.lower(), "Canada", name))
    for name in AUSTRALIA:
        out.append((name.lower(), "Australia", name))
    return sorted(out, key=lambda t: -len(t[0]))


_NAMES = _names()
# 'New York' and 'Washington' alone are the city or the person far more often than the state: they count only as 'New York, NY'-style codes or inside a longer full phrase ('New York State')
_CODE = re.compile(r"(?<=[A-Za-zÀ-ɏ\.])\s*,\s*([A-Z]{2})(?=$|[\s,.;|)\-–—/]|\d)")


def country_from_region(text: str) -> tuple[str, str] | None:
    """(country, what matched) when the text names a state or province of exactly one of United States, Canada or Australia; else None."""
    t = text or ""
    low = re.sub(r"\s+", " ", t.lower())
    found: dict[str, str] = {}
    for name, country, label in _NAMES:
        if re.search(rf"(?<![a-z]){re.escape(name)}(?![a-z])", low):
            found.setdefault(country, label)
    for m in _CODE.finditer(t):
        code = m.group(1)
        if code in _SHARED_CODES:                                          # WA / NT: two countries share them, so the sentence is ambiguous and nothing is concluded
            return None
        tail = t[m.end(): m.end() + 3]
        if code in _WORDLIKE and tail[:1] == " " and tail[1:2].islower():     # ', IN the', ', OR so', ', ON the': an English word in capitals, not a region
            continue
        if code in CANADA:
            found.setdefault("Canada", f"{code} ({CANADA[code]})")
        elif code in US:
            found.setdefault("United States", f"{code} ({US[code]})")
    if len(found) != 1:
        return None
    country = next(iter(found))
    return country, found[country]


def country_matches(value: str, country: str) -> bool:
    """Is `value` ('USA', 'United States', 'Canada') a name of `country` as the lookup spells it?"""
    v = re.sub(r"[^a-z ]+", " ", (value or "").lower())
    v = " ".join(v.split())
    return v in COUNTRY_ALIASES.get(country, {country.lower()})
