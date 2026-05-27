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
    current_density: Optional[int]
    confidence: float
    anchor_found: bool
    anchor_sentence: Optional[str]

    def to_dict(self) -> dict:
        return asdict(self)
