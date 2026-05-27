from pathlib import Path
from typing import Optional

import spacy

from .anchor_extractor import AnchorExtractor
from .config import ELECTROLYTE_PATTERN, SPACY_MODEL
from .logger import get_parser_logger
from .material_extractor import MaterialExtractor
from .pdf_reader import PDFReader
from .schemas import OERRecord
from .substrate_extractor import SubstrateExtractor

logger = get_parser_logger()


class Parser:
    """Pipeline orchestrator for deterministic OER extraction."""

    def __init__(self) -> None:
        nlp = spacy.load(SPACY_MODEL)
        self.pdf_reader = PDFReader()
        self.material_extractor = MaterialExtractor(nlp=nlp)
        self.substrate_extractor = SubstrateExtractor(nlp=nlp)
        self.anchor_extractor = AnchorExtractor()

    def parse_pdf(self, pdf_path: Path) -> OERRecord:
        logger.info(f"Extraindo dados de: {pdf_path.name}")
        blocks = self.pdf_reader.extract(pdf_path)
        anchor_data = self.anchor_extractor.extract(blocks["full_text"])
        
        material = self.material_extractor.extract(blocks["title"], blocks["abstract"], anchor_data["anchor_sentence"])
        substrate = self.substrate_extractor.extract(blocks["full_text"])
        electrolyte = self._extract_electrolyte(blocks["full_text"])

        
        confidence = self._calculate_confidence(
            material=material,
            substrate=substrate,
            electrolyte=electrolyte,
            anchor_found=bool(anchor_data["anchor_found"]),
            overpotential_mV=anchor_data["overpotential_mV"],
        )

        record = OERRecord(
            doi=blocks["doi"],
            source_pdf=pdf_path.name,
            title=blocks["title"],
            abstract=blocks["abstract"],
            material=material,
            substrate=substrate,
            electrolyte=electrolyte,
            overpotential_mV=anchor_data["overpotential_mV"],
            current_density=anchor_data["current_density"],
            confidence=confidence,
            anchor_found=bool(anchor_data["anchor_found"]),
            anchor_sentence=anchor_data["anchor_sentence"],
        )
        logger.info(
            "Extração concluída: %s | material=%s | substrate=%s | eta=%s",
            pdf_path.name,
            record.material,
            record.substrate,
            record.overpotential_mV,
        )
        return record

    def _extract_electrolyte(self, text: Optional[str]) -> Optional[str]:
        if not text:
            return None
        match = ELECTROLYTE_PATTERN.search(text)
        if not match:
            return None
        return f"{match.group(1)} M {match.group(2).upper()}"

    def _calculate_confidence(
        self,
        material: Optional[str],
        substrate: Optional[str],
        electrolyte: Optional[str],
        anchor_found: bool,
        overpotential_mV: Optional[int],
    ) -> float:
        score = 0.0
        if material:
            score += 0.25
        if substrate:
            score += 0.20
        if electrolyte:
            score += 0.10
        if anchor_found:
            score += 0.20
        if overpotential_mV is not None:
            score += 0.25
        return round(score, 2)