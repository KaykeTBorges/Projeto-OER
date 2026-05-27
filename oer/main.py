import argparse
import csv

from .config import OUTPUT_DIR, PDF_DIR
from .logger import get_pipeline_logger
from .parser import Parser
from .scraper import Scraper

logger = get_pipeline_logger()
CSV_FIELDS = [
    "doi",
    "source_pdf",
    "title",
    "abstract",
    "material",
    "substrate",
    "electrolyte",
    "overpotential_mV",
    "current_density",
    "confidence",
    "anchor_found",
    "anchor_sentence",
]


def _load_processed_pdfs(output_path):
    processed = set()
    if not output_path.exists():
        return processed

    with output_path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            source_pdf = (row.get("source_pdf") or "").strip()
            if source_pdf:
                processed.add(source_pdf)
    return processed


def _parse_args():
    parser = argparse.ArgumentParser(description="Pipeline OER: scrape + extract")
    parser.add_argument(
        "--reprocess",
        action="store_true",
        help="Reprocessa PDFs mesmo que já estejam no CSV",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    PDF_DIR.mkdir(parents=True, exist_ok=True)

    output_path = OUTPUT_DIR / "oer_records.csv"
    processed_pdfs = set() if args.reprocess else _load_processed_pdfs(output_path)

    scraper = Scraper()
    parser = None
    total_articles = 0
    total_processed = 0

    file_exists = output_path.exists()
    with output_path.open("a", encoding="utf-8", newline="") as out_file:
        writer = csv.DictWriter(out_file, fieldnames=CSV_FIELDS)
        if not file_exists or output_path.stat().st_size == 0:
            writer.writeheader()

        for page, articles in scraper.iter_article_pages():
            if not articles:
                logger.warning("Nenhum artigo na página %s — verifique seletores ou bloqueio da Nature", page)
                continue

            total_articles += len(articles)
            for article in articles:
                already_downloaded = scraper.is_already_downloaded(article)
                pdf_path = scraper.download_pdf(article)
                if pdf_path is None:
                    logger.warning("PDF indisponível para: %s", article["title"])
                    continue

                if pdf_path.name in processed_pdfs:
                    logger.info("PDF já processado, pulando extração: %s", pdf_path.name)
                    continue

                if parser is None:
                    logger.info("Carregando modelo spaCy para extração...")
                    parser = Parser()

                if already_downloaded:
                    logger.info("PDF já baixado, iniciando extração: %s", pdf_path.name)
                else:
                    logger.info("PDF baixado agora, iniciando extração: %s", pdf_path.name)

                record = parser.parse_pdf(pdf_path)
                writer.writerow(record.to_dict())
                out_file.flush()
                processed_pdfs.add(pdf_path.name)
                total_processed += 1
                logger.info("Registro salvo no CSV: %s", pdf_path.name)

    if total_articles == 0:
        logger.error(
            "Busca concluída sem artigos. Possíveis causas: HTML da Nature mudou, "
            "bloqueio de rede ou query sem resultados."
        )
    else:
        logger.info(
            "Pipeline finalizado: %s artigos encontrados, %s extraídos nesta execução",
            total_articles,
            total_processed,
        )


if __name__ == "__main__":
    main()
