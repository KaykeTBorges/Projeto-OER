from typing import Optional

import spacy
from spacy.language import Language
from spacy.matcher import PhraseMatcher

from . import config


class SubstrateExtractor:
    """Deterministic extractor for substrate/support electrodes."""

    def __init__(self, nlp: Optional[Language] = None) -> None:
        self.nlp = nlp or spacy.load(config.SPACY_MODEL)
        self.matcher = PhraseMatcher(self.nlp.vocab, attr="LOWER")
        self.alias_to_normalized = {}
        self._build_matcher()
        self._build_entity_ruler()

    def _build_matcher(self) -> None:
        patterns = []
        for normalized, aliases in config.SUBSTRATE_PATTERNS.items():
            for alias in aliases:
                self.alias_to_normalized[alias.lower()] = normalized
                patterns.append(self.nlp.make_doc(alias))
        self.matcher.add("SUBSTRATE", patterns)

    def _build_entity_ruler(self) -> None:
        if "entity_ruler" in self.nlp.pipe_names:
            self.nlp.remove_pipe("entity_ruler")
        ruler = self.nlp.add_pipe("entity_ruler", before="ner")
        patterns = []
        for normalized, aliases in config.SUBSTRATE_PATTERNS.items():
            for alias in aliases:
                patterns.append({"label": "SUBSTRATE", "pattern": alias, "id": normalized})
        ruler.add_patterns(patterns)

    def extract(self, text: Optional[str]) -> Optional[str]:
        if not text:
            return None
        doc = self.nlp(text)

        for ent in doc.ents:
            if ent.label_ == "SUBSTRATE":
                return ent.ent_id_ or self.alias_to_normalized.get(ent.text.lower())

        matches = self.matcher(doc)
        if not matches:
            return None
        _, start, end = matches[0]
        return self.alias_to_normalized.get(doc[start:end].text.lower())
