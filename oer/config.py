from pathlib import Path
import re

BASE_DIR = Path(__file__).resolve().parent.parent
PDF_DIR = BASE_DIR / "pdfs"
OUTPUT_DIR = BASE_DIR / "output"
LOGS_DIR = BASE_DIR / "logs"

BASE_URL = "https://www.nature.com/search"
ARTICLE_BASE_URL = "https://www.nature.com"
SEARCH_QUERY = '"machine learning" AND ("oxygen evolution reaction" OR "OER")'
MAX_PAGES = 3
REQUEST_DELAY = 1.5
REQUEST_TIMEOUT_SECONDS = 25

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    )
}

SPACY_MODEL = "en_core_web_sm"
MAX_FRONT_PAGES = 2
ANCHOR_CONTEXT_CHARS = 300

DOI_PATTERN = re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+\b", re.I)
ABSTRACT_PATTERN = re.compile(
    r"\babstract\b[\s:\-]*(.*?)(?:\bintroduction\b|\bbackground\b|\bkeywords\b)",
    re.I | re.S,
)
ANCHOR_PATTERN = re.compile(
    r"(?:\bj\s*=\s*)?10\s*mA\s*(?:cm(?:[-−]2|\^-2)|/cm2)|η\s*10",
    re.I,
)
OVERPOTENTIAL_PATTERN = re.compile(r"(\d+(?:\.\d+)?)\s*mV", re.I)
ELECTROLYTE_PATTERN = re.compile(
    r"(\d+\.?\d*)\s*M\s*(KOH|NaOH|H2SO4|HClO4|KPi|PBS)",
    re.I,
)

SUBSTRATE_PATTERNS = {

    # Nickel foam
    "nickel foam": [
        "nickel foam",
        "ni foam",
        "nf",
    ],

    # Carbon cloth
    "carbon cloth": [
        "carbon cloth",
        "cc",
    ],

    # Carbon paper
    "carbon paper": [
        "carbon paper",
        "cp",
    ],

    # Glassy carbon
    "glassy carbon": [
        "glassy carbon",
        "gc",
        "gce",
        "glassy carbon electrode",
    ],

    # FTO
    "fluorine-doped tin oxide": [
        "fto",
        "fluorine-doped tin oxide",
    ],

    # ITO
    "indium tin oxide": [
        "ito",
        "indium tin oxide",
    ],

    # Titanium
    "titanium mesh": [
        "ti mesh",
        "titanium mesh",
    ],

    "titanium foil": [
        "ti foil",
        "titanium foil",
    ],

    # Nickel
    "nickel mesh": [
        "ni mesh",
        "nickel mesh",
    ],

    "nickel foil": [
        "ni foil",
        "nickel foil",
    ],

    # Copper
    "copper foam": [
        "cu foam",
        "copper foam",
    ],

    "copper foil": [
        "cu foil",
        "copper foil",
    ],

    # Stainless steel
    "stainless steel mesh": [
        "ss mesh",
        "stainless steel mesh",
    ],

    "stainless steel foam": [
        "ss foam",
        "stainless steel foam",
    ],

    # Gold
    "gold foil": [
        "au foil",
        "gold foil",
    ],

    # Silver
    "silver foam": [
        "ag foam",
        "silver foam",
    ],

    # Graphite / carbon
    "graphite rod": [
        "graphite rod",
    ],

    "carbon felt": [
        "carbon felt",
        "cf",
    ],

    "graphene foam": [
        "graphene foam",
    ],

    # Misc
    "mesh": [
        "mesh",
    ],

    "foam": [
        "foam",
    ],

    "foil": [
        "foil",
    ],
}

MATERIAL_DOMAIN_STOPWORDS = {
    "oxygen evolution reaction",
    "electrocatalyst",
    "water splitting",
    "catalyst activity",
    "oer",
    "oxygen evolution",
    "reaction",
    "catalyst",
    "electrocatalysts",
    "article",
    "articles",
    "letter",
    "letters",
    "nature",
    "communications",
    "npj",
    "computational materials",
    "2d materials",
    "applications",
    "www.nature.com",
    "published online",
}