import re
from pathlib import Path
from typing import Dict, Optional

import fitz

from . import config


class PDFReader:
    """Read PDF files and split metadata text from full text."""

    # Frases que indicam PDF de acesso restrito/pago
    _PAYWALL_PHRASES = (
        "buy this article",
        "buy or subscribe",
        "access through your institution",
        "this is a preview of subscription content",
        "subscribe to this journal",
        "purchase this article",
        "get full access",
        "rent or buy",
        "log in to check access",
        "institutional login",
    )

    @staticmethod
    def is_paywalled(text: str) -> bool:
        """Retorna True se o texto indica que o PDF é pago/restrito."""
        lowered = text.lower()
        return any(phrase in lowered for phrase in PDFReader._PAYWALL_PHRASES)

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
        paywalled = self.is_paywalled(full_text)

        return {
            "title": self.extract_title(front_text),
            "abstract": self.extract_abstract(front_text),
            "doi": self.extract_doi(front_text),
            "front_text": front_text,
            "full_text": full_text,
            "paywalled": paywalled,
        }

    def extract_title(self, front_text: str) -> Optional[str]:
        lines = [self._clean_line(line) for line in front_text.splitlines()]
        lines = [line for line in lines if line]
        if not lines:
            return None

        start_index = self._title_start_index(lines)
        title_lines = []

        for line in lines[start_index:]:
            normalized = self._clean_line(line)
            folded = normalized.casefold()

            if not title_lines and self._is_title_noise(normalized):
                continue
            if title_lines and self._looks_like_author_line(normalized):
                break
            if title_lines and folded.startswith(("abstract", "received:", "check for updates", "show authors")):
                break
            if title_lines and self._is_article_meta(normalized):
                break
            if self._is_title_noise(normalized):
                continue

            title_lines.append(normalized)
            if len(" ".join(title_lines)) >= 180:
                break

        if not title_lines:
            return None
        return self._clean_joined_title(" ".join(title_lines))

    def _title_start_index(self, lines: list[str]) -> int:
        for index, line in enumerate(lines):
            if line.casefold().startswith("published:"):
                return index + 1

        for index, line in enumerate(lines):
            folded = line.casefold()
            if folded.startswith("https://doi.org/") or folded.startswith("doi:"):
                return index + 1

        for index, line in enumerate(lines):
            if not self._is_title_noise(line) and not self._is_article_meta(line):
                return index
        return 0

    def _clean_line(self, line: str) -> str:
        line = line.replace("\u00a0", " ").strip()
        line = re.sub(r"^[•\-\*]\s*", "", line)
        return " ".join(line.split())

    def _is_title_noise(self, line: str) -> bool:
        folded = line.casefold()
        noise = (
            "skip to main content",
            "thank you for visiting nature.com. you are using a browser version",
            "with limited support for css. to obtain the best experience, we",
            "recommend you use a more up to date browser (or turn off",
            "compatibility mode in internet explorer). in the meantime, to",
            "ensure continued support, we are displaying the site without styles",
            "and javascript.",
            "advertisement",
            "[image]",
            "view all journals",
            "search",
            "log in",
            "content explore content",
            "about the journal",
            "publish with us",
            "subscribe",
            "sign up for alerts",
            "rss feed",
            "article",
            "review article",
            "communications chemistry",
            "npj | computational materials",
            "nature communications",
            "scientific reports",
        )
        return (
            folded in noise
            or folded.startswith("https://doi.org/")
            or folded.startswith("doi:")
            or folded.startswith("www.")
            or folded.startswith("orcid:")
            or folded.startswith("orcid.org/")
            or bool(re.fullmatch(r"\d+\.\s+.+", folded))
        )

    def _is_article_meta(self, line: str) -> bool:
        folded = line.casefold()
        return (
            folded.startswith("published:")
            or folded.startswith("nature ") and " pages " in folded
            or folded.endswith("cite this article")
            or folded in {"subjects", "metrics details"}
            or folded.endswith("accesses")
            or folded.endswith("citations")
            or folded.endswith("altmetric")
        )

    def _looks_like_author_line(self, line: str) -> bool:
        folded = line.casefold()
        if "orcid" in folded or "show authors" in folded:
            return True
        has_initial = bool(re.search(r"\b[A-Z]\.", line))
        has_affiliation_marker = bool(re.search(r"[A-Za-z][0-9,]{1,}", line))
        has_many_names = line.count(",") >= 2
        simple_name = bool(re.fullmatch(r"[A-Z][A-Za-z.-]+(?:\s+[A-Z][A-Za-z.-]+){1,3}", line))
        return has_initial or has_affiliation_marker or has_many_names or simple_name

    def _clean_joined_title(self, title: str) -> str:
        title = re.sub(r"\s+([/])\s+", r"\1", title)
        title = re.sub(r"([-/])\s+", r"\1", title)
        title = re.sub(r"\s+", " ", title)
        return title.strip(" .")

    def extract_abstract(self, front_text: str) -> Optional[str]:
        # 1) Tenta com cabeçalho explícito "Abstract"
        match = config.ABSTRACT_PATTERN.search(front_text)
        if match:
            return " ".join(match.group(1).split())

        # 2) Fallback posicional para PDFs estilo Nature (sem cabeçalho "Abstract").
        # Estrutura típica: Article | DOI | Título | Autores | ABSTRACT | Introduction
        # O abstract começa após o bloco de autores e termina antes de "Introduction".
        lines = front_text.splitlines()

        # Localiza o índice da primeira linha de seção (Introduction / Results / etc.)
        section_re = re.compile(
            r"^\s*(?:introduction|results(?: and discussion)?|background|methods)\s*$",
            re.I,
        )
        section_idx = len(lines)
        for i, line in enumerate(lines):
            if section_re.match(line):
                section_idx = i
                break

        _NOISE_RE = re.compile(
            r"^(?:https?://|www\.|doi:|open|article|review|letter|check for updates"
            r"|received|published|accepted|thank you for visiting"
            r"|nature catalysis|nature materials|nature chemistry|nature communications"
            r"|nature energy|nature nanotechnology|scientific reports"
            r"|cite this article|\d+k accesses|\d+ accesses|orcid"
            r"|\d+\s*$|\d{4}\s+\d+:\d+|\(c\)|©|\u00a9)",
            re.I,
        )
        _AUTHOR_MARKER_RE = re.compile(
            r"""
            (?:
                \d+\s*[,;]?\s*$                    # linha só com número
                | \w+.*@\w+\.\w+                    # email
                | \w+\d+[,;]                        # Sobrenome1, (superscript colado)
                | \b\w+\s+\d+[,;]\d                 # Wu 1,2 (superscript separado)
                | (?:\w+\s*,\s*){3,}                # lista com 3+ vírgulas
                | orcid
                | \b(?:university|institute|department|laboratory|
                       national\s+lab|argonne|harvard|cambridge|stanford|
                       correspond|correspondence|email:)\b
            )
            """,
            re.I | re.X,
        )

        def _is_author_line(text: str) -> bool:
            """Normaliza \xa0 → espaço antes de checar padrões de autor."""
            return bool(_AUTHOR_MARKER_RE.search(text.replace("\xa0", " ")))

        def _collect_from(start: int) -> str:
            """Coleta linhas a partir de `start` até a seção ou marcador de afiliação."""
            collected: list[str] = []
            for ln in lines[start:section_idx]:
                s = ln.strip().replace("\xa0", " ")
                if collected and _is_author_line(s):
                    break
                if s:
                    collected.append(s)
            raw = " ".join(collected)
            raw = re.sub(r"-\s+", "", raw)  # desfaz hifenização de word-wrap
            return " ".join(raw.split())

        # Varre as linhas e testa cada candidata a início de abstract
        for i, line in enumerate(lines[:section_idx]):
            stripped = line.strip().replace("\xa0", " ")
            if not stripped:
                continue
            if len(stripped) < 30:
                continue
            if _NOISE_RE.match(stripped):
                continue
            if _is_author_line(stripped):
                continue
            if not stripped[0].isupper():
                continue

            # Candidato encontrado — coleta o bloco e valida
            candidate = _collect_from(i)
            # Descarta se não há ponto (é título multi-linha, não abstract)
            if "." not in candidate:
                continue
            if not (80 <= len(candidate) <= 3000):
                continue
            return candidate

        return None


    def extract_doi(self, front_text: str) -> Optional[str]:
        match = config.DOI_PATTERN.search(front_text)
        if not match:
            return None
        return match.group(0)