from dataclasses import asdict, dataclass
from typing import Optional


@dataclass
class OERRecord:
    doi: Optional[str]
    source_pdf: str
    title: Optional[str]
    abstract: Optional[str]
    material: Optional[str]
    substrate: Optional[str]
    electrolyte: Optional[str]
    overpotential_mV: Optional[int]
    current_density: Optional[float]
    potential_V: Optional[float]
    performance_source: Optional[str]
    confidence: float
    extraction_note: str
    anchor_found: bool
    anchor_sentence: Optional[str]

    def to_dict(self) -> dict:
        return asdict(self)
