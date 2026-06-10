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


class PaywalledPDFError(Exception):
    """Levantada quando o PDF detectado é de acesso restrito (paywall)."""


class Parser:
    """Pipeline orchestrator for deterministic OER extraction."""

    def __init__(self) -> None:
        # roda o modelo sci
        nlp = spacy.load(SPACY_MODEL)
        # chama o pdfreader que estava lá
        self.pdf_reader = PDFReader()
        # os extractores de material e substrato, mas o substrato não precisa tanto de nlp, porque temos uma lista para eles
        # mas o nlp é usado para matcher e mudar seu entity ruler padrão para o nosso, com a nossa lista
        self.material_extractor = MaterialExtractor()
        self.substrate_extractor = SubstrateExtractor(nlp=nlp)
        self.anchor_extractor = AnchorExtractor()

    def parse_pdf(self, pdf_path: Path) -> OERRecord:
        logger.info(f"Extraindo dados de: {pdf_path.name}")
        blocks = self.pdf_reader.extract(pdf_path)

        if blocks.get("paywalled"):
            raise PaywalledPDFError(f"PDF com acesso restrito (paywall): {pdf_path.name}")

        anchor_data = self.anchor_extractor.extract(
            blocks["full_text"],
            blocks["abstract"],
        )
        
        material = self.material_extractor.extract(
            blocks["title"],
            blocks["abstract"],
            anchor_data["anchor_sentence"],
            anchor_data["overpotential_mV"],
        )
        substrate = self.substrate_extractor.extract(blocks["full_text"])
        electrolyte = self._extract_electrolyte(blocks["full_text"])

        
        confidence = self._calculate_confidence(
            material=material,
            substrate=substrate,
            electrolyte=electrolyte,
            anchor_found=bool(anchor_data["anchor_found"]),
            overpotential_mV=anchor_data["overpotential_mV"],
        )

        extraction_note = self._extraction_note(
            text=blocks["full_text"],
            material=material,
            anchor_found=bool(anchor_data["anchor_found"]),
            overpotential_mV=anchor_data["overpotential_mV"],
            current_density=anchor_data["current_density"],
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
            potential_V=anchor_data["potential_V"],
            performance_source=anchor_data["performance_source"],
            confidence=confidence,
            extraction_note=extraction_note,
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


    def _extraction_note(
        self,
        text: Optional[str],
        material: Optional[str],
        anchor_found: bool,
        overpotential_mV: Optional[int],
        current_density: Optional[float],
    ) -> str:
        is_nonstandard_current = current_density is not None and abs(float(current_density) - 10.0) > 1e-6
        if material and anchor_found and overpotential_mV is not None:
            return "nonstandard_current_density" if is_nonstandard_current else "complete"
        if anchor_found and overpotential_mV is not None and not material:
            return "anchor_missing_material"
        if material and not anchor_found:
            return "material_without_anchor"
        if not self._has_oer_signal(text):
            return "no_oer_signal"
        return "missing_anchor"

    def _has_oer_signal(self, text: Optional[str]) -> bool:
        if not text:
            return False
        folded = text.casefold()
        return "oer" in folded or "oxygen evolution" in folded or "water oxidation" in folded

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