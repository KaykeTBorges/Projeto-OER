from pathlib import Path
import re

BASE_DIR = Path(__file__).resolve().parent.parent
PDF_DIR = BASE_DIR / "pdfs"
OUTPUT_DIR = BASE_DIR / "output"
LOGS_DIR = BASE_DIR / "logs"

BASE_URL = "https://www.nature.com/search"
ARTICLE_BASE_URL = "https://www.nature.com"
SEARCH_QUERY = '"oxygen evolution reaction" OR "OER"'
MAX_PAGES = 10
REQUEST_DELAY = 1.5
REQUEST_TIMEOUT_SECONDS = 25

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    )
}

SPACY_MODEL = "en_core_sci_lg"
MAX_FRONT_PAGES = 3
ANCHOR_CONTEXT_CHARS = 600

DOI_PATTERN = re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+\b", re.I)
ABSTRACT_PATTERN = re.compile(
    r"\babstract\b[\s:\-]*(.*?)(?:\bintroduction\b|\bbackground\b|\bkeywords\b)",
    re.I | re.S,
)

ANCHOR_PATTERN = re.compile(
    r"""
    (?:
        # j = 10 mA cm⁻² (forma direta)
        (?:\bj\s*=\s*)?
        (?P<current_density>\d+(?:\.\d+)?)\s*
        (?P<current_unit>mA|A)\s*
        (?:
            cm\s*[-−–—]?\s*2           # cm-2, cm−2
            |cm\s*\^\s*[-−–—]?\s*2     # cm^-2
            |cm\s*[⁻\u207B]\s*[²2\u00B2]  # cm⁻²
            |/\s*cm\s*[²2\u00B2]?      # /cm2, /cm²
        )
    |
        # η@10 ou η@10mA
        η\s*[@＠]\s*(?P<eta_current_density>\d+(?:\.\d+)?)
    |
        # η₁₀ (subscript unicode)
        η(?P<eta_sub>[₀₁₂₃₄₅₆₇₈₉]+)
    |
        # @10 mA cm⁻² (sem j=)
        @\s*(?P<current_density3>\d+(?:\.\d+)?)\s*
        (?P<current_unit3>mA|A)\s*
        (?:
            cm\s*[-−–—]?\s*2
            |cm\s*\^\s*[-−–—]?\s*2
            |cm\s*[⁻\u207B]\s*[²2\u00B2]
            |/\s*cm\s*[²2\u00B2]?
        )
    )
    """,
    re.I | re.X,
)

OVERPOTENTIAL_PATTERN = re.compile(
    r"(?:~|≈|ca\.?\s*|about\s*)?(\d+(?:\.\d+)?)\s*(?:±\s*\d+(?:\.\d+)?)?\s*mV",
    re.I,
)

_CURRENT_DENSITY_UNIT = (
    r"(?:"
    r"cm\s*[-−–—]?\s*2"
    r"|cm\s*\^\s*[-−–—]?\s*2"
    r"|cm\s*[⁻\u207B]\s*[²2\u00B2]"
    r"|/\s*cm\s*[²2\u00B2]?"
    r")"
)

PERFORMANCE_PAIR_PATTERN = re.compile(
    rf"""
    (?P<overpotential>\d+(?:\.\d+)?)\s*mV
    (?:(?!dec).){{0,120}}?
    (?:at\s+(?:a\s+)?(?:current\s+density\s+of\s+)?)?
    (?P<current_density>\d+(?:\.\d+)?)\s*(?P<current_unit>mA|A)\s*
    {_CURRENT_DENSITY_UNIT}
    """,
    re.I | re.X,
)

POTENTIAL_VS_RHE_PATTERN = re.compile(
    rf"""
    (?P<potential>\d+(?:\.\d+)?)\s*V
    (?:\s*(?:vs\.?\s*)?RHE)?
    (?:(?!dec).){{0,100}}?
    (?:at\s+(?:a\s+)?(?:current\s+density\s+of\s+)?)?
    (?P<current_density>\d+(?:\.\d+)?)\s*(?P<current_unit>mA|A)\s*
    {_CURRENT_DENSITY_UNIT}
    """,
    re.I | re.X,
)

RHE_REFERENCE_V = 1.23

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
        "fluorine doped tin oxide"
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

CHEMICAL_ELEMENTS = {
    "H", "He", "Li", "Be", "B", "C", "N", "O", "F", "Ne", "Na", "Mg", "Al", "Si", "P", "S",
    "Cl", "Ar", "K", "Ca", "Sc", "Ti", "V", "Cr", "Mn", "Fe", "Co", "Ni", "Cu", "Zn", "Ga",
    "Ge", "As", "Se", "Br", "Kr", "Rb", "Sr", "Y", "Zr", "Nb", "Mo", "Tc", "Ru", "Rh",
    "Pd", "Ag", "Cd", "In", "Sn", "Sb", "Te", "I", "Xe", "Cs", "Ba", "La", "Ce", "Pr",
    "Nd", "Pm", "Sm", "Eu", "Gd", "Tb", "Dy", "Ho", "Er", "Tm", "Yb", "Lu", "Hf", "Ta",
    "W", "Re", "Os", "Ir", "Pt", "Au", "Hg", "Tl", "Pb", "Bi", "Po", "At", "Rn", "Fr", "Ra",
    "Ac", "Th", "Pa", "U", "Np", "Pu", "Am", "Cm", "Bk", "Cf", "Es", "Fm", "Md", "No", "Lr",
}

FORMULA_TOKEN_PATTERN = re.compile(
    r"(?<![A-Za-z0-9])(?:[A-Z][a-z]?[0-9xδ+]*(?:\.[0-9]+)?)+(?:O[0-9xδ+]*)?(?![A-Za-z0-9])"
)
COMPOUND_PATTERN = re.compile(
    r"(?<![A-Za-z0-9])"
    r"(?:[A-Z][A-Za-z0-9.δ+]*)(?:\s*(?:[/@]|[-−–])\s*(?:[A-Z][A-Za-z0-9.δ+]*))*"
    r"(?![A-Za-z0-9])"
)
MATERIAL_DESCRIPTOR_PATTERN = re.compile(
    r"^(?:oxide|oxides|hydroxide|hydroxides|oxyhydroxide|oxyhydroxides|ldh|mof|mxene|"
    r"perovskite|popsicle|sticks|nanofibers|nanosheets|nanorods|nanoparticles|"
    r"single|atoms|sites|solid|solution|phase)\b",
    re.I,
)
MATERIAL_STOP_AFTER_PATTERN = re.compile(
    r"^(?:for|with|at|in|on|by|from|as|and|or|but|which|that|exhibit|exhibits|"
    r"achieve|achieves|achieved|show|shows|showed|demonstrate|demonstrates)\b",
    re.I,
)

MATERIAL_INVALID_UNITS = (" ma", "mv", " cm", "rhe", "fig", "doi")
MATERIAL_VALID_ACRONYMS = frozenset({"ldh", "mof", "mxene"})
GENERIC_MATERIAL_PHRASES = frozenset({
    "perovskite",
    "oxide",
    "oxides",
    "hydroxide",
    "hydroxides",
    "oxyhydroxide",
})
MATERIAL_CHEMICAL_TOKENS = (
    "oxide",
    "hydroxide",
    "oxyhydroxide",
    "ldh",
    "mof",
    "mxene",
    "perovskite",
)
EXCLUDED_FORMULA_ACRONYMS = frozenset({
    "OER", "HER", "ORR", "RHE", "DFT", "XRD", "SEM", "TEM", "ML", "PDF",
})
MATERIAL_SCORE_TOKENS = (
    "oxide",
    "hydroxide",
    "oxyhydroxide",
    "ldh",
    "perovskite",
)