import re
import time
from pathlib import Path
from typing import Dict, Iterator, List, Tuple

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from . import config
from .logger import get_scraper_logger

logger = get_scraper_logger()

# Seletores alternativos — a Nature muda o HTML com frequência
ARTICLE_LINK_SELECTORS = (
    "article.u-full-height h3 a",
    "li.app-article-list-row__item h3 a",
    "h3.c-card__title a",
    "article h3 a[href*='/articles/']",
)

PDF_LINK_SELECTORS = (
    {"attrs": {"data-track-action": "download pdf"}},
    {"attrs": {"data-track-action": "Download PDF"}},
    {"attrs": {"data-test": "download-pdf"}},
)


class Scraper:
    """Fetch article pages from Nature and download PDFs."""

    def __init__(self):
        self.base_url = config.BASE_URL
        self.search_query = config.SEARCH_QUERY
        self.max_pages = config.MAX_PAGES
        self.pdf_dir = config.PDF_DIR
        self.pdf_dir.mkdir(parents=True, exist_ok=True)

        self.session = requests.Session()
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("https://", adapter)
        self.session.headers.update(config.HEADERS)

    def _sanitize_filename(self, title: str) -> str:
        title_clean = re.sub(r"[^\w\s-]", "", title).strip().replace(" ", "_")
        return f"{title_clean[:60]}.pdf"

    def _parse_articles(self, soup: BeautifulSoup) -> List[Dict[str, str]]:
        articles: List[Dict[str, str]] = []
        seen_urls: set[str] = set()

        for selector in ARTICLE_LINK_SELECTORS:
            for title_tag in soup.select(selector):
                href = title_tag.get("href")
                if not href:
                    continue
                url = href if href.startswith("http") else config.ARTICLE_BASE_URL + href
                if url in seen_urls:
                    continue
                title = title_tag.get_text(strip=True)
                if not title:
                    continue
                seen_urls.add(url)
                articles.append({"title": title, "url": url})

        return articles

    def iter_article_pages(self) -> Iterator[Tuple[int, List[Dict[str, str]]]]:
        """Busca uma página por vez e devolve artigos imediatamente."""
        for page in range(1, self.max_pages + 1):
            logger.info("Buscando página %s", page)
            articles: List[Dict[str, str]] = []

            # A Nature às vezes responde uma página temporária sem os cards.
            # Retentamos algumas vezes antes de concluir que a página veio vazia.
            for attempt in range(1, 4):
                response = self.session.get(
                    self.base_url,
                    params={"q": self.search_query, "page": page},
                    timeout=config.REQUEST_TIMEOUT_SECONDS,
                )
                response.raise_for_status()

                soup = BeautifulSoup(response.text, "html.parser")
                articles = self._parse_articles(soup)
                if articles:
                    break

                page_title = soup.title.string.strip() if soup.title and soup.title.string else "sem título"
                logger.warning(
                    "Página %s vazia na tentativa %s/3 (title=%s, html_len=%s).",
                    page,
                    attempt,
                    page_title,
                    len(response.text),
                )
                time.sleep(config.REQUEST_DELAY * attempt)

            logger.info("Página %s: %s artigos encontrados", page, len(articles))
            yield page, articles
            time.sleep(config.REQUEST_DELAY)

    def search_articles(self) -> List[Dict[str, str]]:
        articles: List[Dict[str, str]] = []
        for _, page_articles in self.iter_article_pages():
            articles.extend(page_articles)
        logger.info("Total de artigos na busca: %s", len(articles))
        return articles

    def get_pdf_path(self, article: Dict) -> Path:
        return self.pdf_dir / self._sanitize_filename(article["title"])

    def is_already_downloaded(self, article: Dict) -> bool:
        return self.get_pdf_path(article).exists()

    def _find_pdf_url(self, soup: BeautifulSoup) -> str | None:
        for selector in PDF_LINK_SELECTORS:
            pdf_tag = soup.find("a", **selector)
            if pdf_tag and pdf_tag.get("href"):
                href = pdf_tag["href"]
                return href if href.startswith("http") else config.ARTICLE_BASE_URL + href

        meta_pdf = soup.find("meta", attrs={"name": "citation_pdf_url"})
        if meta_pdf and meta_pdf.get("content"):
            return meta_pdf["content"]

        for link in soup.find_all("a", href=True):
            href = link["href"]
            if href.endswith(".pdf"):
                return href if href.startswith("http") else config.ARTICLE_BASE_URL + href

        return None

    def download_pdf(self, article: Dict) -> Path | None:
        filepath = self.get_pdf_path(article)

        if filepath.exists():
            logger.info("PDF já existe, pulando download: %s", filepath.name)
            return filepath

        resp = self.session.get(article["url"], timeout=config.REQUEST_TIMEOUT_SECONDS)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        pdf_url = self._find_pdf_url(soup)
        if not pdf_url:
            logger.warning("Link de PDF não encontrado: %s", article["title"])
            return None

        pdf_resp = self.session.get(
            pdf_url,
            stream=True,
            timeout=config.REQUEST_TIMEOUT_SECONDS,
        )
        pdf_resp.raise_for_status()
        with filepath.open("wb") as f:
            for chunk in pdf_resp.iter_content(8192):
                f.write(chunk)

        logger.info("Baixado: %s", filepath.name)
        return filepath
