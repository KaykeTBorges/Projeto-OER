import re
from typing import Dict, Optional

from . import config


class AnchorExtractor:
    """Extract overpotential around j=10 mA cm^-2 anchor mentions."""

    def extract(self, full_text: Optional[str]) -> Dict[str, object]:
        if not full_text:
            return self._empty_result()

        for match in config.ANCHOR_PATTERN.finditer(full_text):
            context = self._window(full_text, match.start(), match.end())
            overpotential = self._find_overpotential(context)
            if overpotential is not None:
                sentence = self._extract_sentence(context)
                return {
                    "overpotential_mV": int(round(overpotential)),
                    "current_density": 10,
                    "anchor_found": True,
                    "anchor_sentence": sentence,
                }

        return self._empty_result()

    def _window(self, text: str, start: int, end: int) -> str:
        left = max(0, start - config.ANCHOR_CONTEXT_CHARS)
        right = min(len(text), end + config.ANCHOR_CONTEXT_CHARS)
        return text[left:right]

    def _find_overpotential(self, context: str) -> Optional[float]:
        candidates = []
        for match in config.OVERPOTENTIAL_PATTERN.finditer(context):
            value = float(match.group(1))
            if 100 <= value <= 1000:
                candidates.append((abs(match.start() - context.lower().find("10")), value))
        if not candidates:
            return None
        candidates.sort(key=lambda item: item[0])
        return candidates[0][1]

    def _extract_sentence(self, context: str) -> str:
        sentences = re.split(r"(?<=[.!?])\s+", " ".join(context.split()))
        for sentence in sentences:
            if config.ANCHOR_PATTERN.search(sentence):
                return sentence.strip()
        return context.strip()

    def _empty_result(self) -> Dict[str, object]:
        return {
            "overpotential_mV": None,
            "current_density": None,
            "anchor_found": False,
            "anchor_sentence": None,
        }
