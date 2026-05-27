from typing import Optional

import spacy
from spacy.language import Language

from . import config


class MaterialExtractor:
    """NLP-driven catalyst extractor using title + abstract."""

    def __init__(self, nlp: Optional[Language] = None) -> None:
        self.nlp = nlp or spacy.load(config.SPACY_MODEL)

    def extract(self, title: Optional[str], abstract: Optional[str], anchor_sentence: Optional[str]) -> Optional[str]:
        """Texto enviado ao spaCy mantém capitalização original (fórmulas/química)."""
        best_candidate = None
        best_score = -1

        sources = [("title", title or ""), ("abstract", abstract or ""), ("anchor_sentence", anchor_sentence or "")]
        for source_name, source_text in sources:
            if not source_text.strip():
                continue

            # Nunca lowercasing antes do NLP — só usamos .lower() em filtros de stopword.
            doc = self.nlp(source_text)
            for chunk in doc.noun_chunks:
                candidate = " ".join(chunk.text.split()).strip(".,;:()[]")
                if not self._is_valid_candidate(candidate):
                    continue

                score = self._score_candidate(candidate, source_name)
                if score > best_score:
                    best_score = score
                    best_candidate = candidate

        return best_candidate

    def _is_valid_candidate(self, candidate: str) -> bool:
        # Comparação de stopwords em minúsculas; candidato preservado com case original.
        candidate_lower = candidate.casefold()
        if not candidate:
            return False
        if len(candidate) < 3 or len(candidate) > 80:
            return False
        if "|" in candidate or "http" in candidate_lower:
            return False
        stopwords = {s.casefold() for s in config.MATERIAL_DOMAIN_STOPWORDS}
        if candidate_lower in stopwords:
            return False
        if any(stop in candidate_lower for stop in stopwords):
            return False
        if not self._has_chemical_signal(candidate):
            return False
        return True

    def _has_chemical_signal(self, text: str) -> bool:
        # Mantém a extração aberta, mas exige algum sinal científico mínimo
        has_digit = any(ch.isdigit() for ch in text)
        has_formula_case = any(ch.isupper() for ch in text) and any(ch.islower() for ch in text)
        has_symbols = any(sym in text for sym in ("-", "/", "@", "(", ")", "."))
        text_folded = text.casefold()
        has_material_token = any(
            token in text_folded
            for token in ("oxide", "hydroxide", "ldh", "mof", "mxene", "perovskite")
        )
        return has_digit or has_formula_case or has_symbols or has_material_token

    def _score_candidate(self, text: str, source_name: str) -> int:
        score = 0
        if any(ch.isdigit() for ch in text):
            score += 3
        if any(ch.isupper() for ch in text):
            score += 2
        if "-" in text or "/" in text:
            score += 2
        if source_name == "title":
            score += 1
        score += min(len(text.split()), 4)
        return score
