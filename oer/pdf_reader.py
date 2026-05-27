from pathlib import Path
from typing import Dict, Optional

import fitz

from . import config


class PDFReader:
    """Read PDF files and split metadata text from full text."""

    def extract(self, pdf_path: Path) -> Dict[str, Optional[str]]:
        doc = fitz.open(pdf_path)
        front_pages = []
        full_pages = []

        for i, page in enumerate(doc):
            text = page.get_text("text")
            if not text:
                continue
            full_pages.append(text)
            if i < config.MAX_FRONT_PAGES:
                front_pages.append(text)

        front_text = "\n".join(front_pages)
        full_text = "\n".join(full_pages)

        return {
            "title": self.extract_title(front_text),
            "abstract": self.extract_abstract(front_text),
            "doi": self.extract_doi(front_text),
            "front_text": front_text,
            "full_text": full_text,
        }

    def extract_title(self, front_text: str) -> Optional[str]:
        lines = [line.strip() for line in front_text.splitlines() if line.strip()]
        if not lines:
            return None
        return lines[0]

    def extract_abstract(self, front_text: str) -> Optional[str]:
        match = config.ABSTRACT_PATTERN.search(front_text)
        if not match:
            return None
        return " ".join(match.group(1).split())

    def extract_doi(self, front_text: str) -> Optional[str]:
        match = config.DOI_PATTERN.search(front_text)
        if not match:
            return None
        return match.group(0)