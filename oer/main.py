import argparse
import csv

from .config import OUTPUT_DIR, PDF_DIR
from .logger import get_pipeline_logger
from .parser import Parser, PaywalledPDFError
from .scraper import Scraper

logger = get_pipeline_logger()

# campos do CSV em ordem fixa — qualquer novo campo precisa ser adicionado aqui
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
    "potential_V",
    "performance_source",
    "confidence",
    "extraction_note",
    "anchor_found",
    "anchor_sentence",
]


def _ensure_csv_schema(output_path):
    # se o arquivo não existe ou está vazio, não tem nada para migrar
    if not output_path.exists() or output_path.stat().st_size == 0:
        return

    with output_path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        # se o schema já está correto, não precisa fazer nada
        if reader.fieldnames == CSV_FIELDS:
            return
        # lê todas as linhas antes de fechar o arquivo para reescrever
        rows = list(reader)

    # reescreve o arquivo inteiro com o schema atualizado
    # linhas antigas que não tinham extraction_note recebem o valor calculado pelo legado
    with output_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for row in rows:
            # garante que todos os campos existam, mesmo que vazios
            normalized = {field: row.get(field, "") for field in CSV_FIELDS}
            # preenche extraction_note para registros antigos que não tinham esse campo
            if not normalized["extraction_note"]:
                normalized["extraction_note"] = _legacy_extraction_note(normalized)
            writer.writerow(normalized)


def _legacy_extraction_note(row):
    # reconstrói o extraction_note para registros antigos que não tinham esse campo
    # usa a mesma lógica do parser atual para manter consistência
    material = (row.get("material") or "").strip()
    anchor_found = (row.get("anchor_found") or "").strip().casefold() == "true"
    overpotential = (row.get("overpotential_mV") or "").strip()
    title = (row.get("title") or "").casefold()
    abstract = (row.get("abstract") or "").casefold()
    anchor_sentence = (row.get("anchor_sentence") or "").casefold()
    text = " ".join((title, abstract, anchor_sentence))

    # ordem de prioridade dos casos, do mais completo para o mais vazio
    if material and anchor_found and overpotential:
        return "complete"
    if anchor_found and overpotential and not material:
        return "anchor_missing_material"
    if material and not anchor_found:
        return "material_without_anchor"
    # verifica se o artigo sequer fala de OER antes de classificar como missing_anchor
    if not any(signal in text for signal in ("oer", "oxygen evolution", "water oxidation")):
        return "no_oer_signal"
    return "missing_anchor"


def _load_processed_pdfs(output_path):
    # carrega os nomes dos PDFs que já foram processados para não reprocessar
    # retorna um set vazio se o arquivo ainda não existe
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
        # se passado, ignora a lista de PDFs já processados e reextrai tudo
        # útil após mudanças nos extractors para atualizar o CSV
        help="Reprocessa PDFs mesmo que já estejam no CSV",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()

    # garante que os diretórios de saída existam antes de qualquer operação
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    PDF_DIR.mkdir(parents=True, exist_ok=True)

    output_path = OUTPUT_DIR / "oer_records.csv"

    # migra o schema se necessário antes de qualquer leitura ou escrita
    _ensure_csv_schema(output_path)

    # se --reprocess foi passado, trata todos os PDFs como não processados
    processed_pdfs = set() if args.reprocess else _load_processed_pdfs(output_path)

    scraper = Scraper()

    # parser é inicializado só quando necessário para evitar carregar o spaCy
    # se todos os PDFs já estiverem processados
    parser = None

    total_articles = 0
    total_processed = 0

    # abre o CSV em modo append para não perder registros anteriores
    file_exists = output_path.exists()
    with output_path.open("a", encoding="utf-8", newline="") as out_file:
        writer = csv.DictWriter(out_file, fieldnames=CSV_FIELDS)

        # escreve o cabeçalho só se o arquivo é novo ou estava vazio
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

                # PDF indisponível pode ser paywall, erro de rede ou artigo sem PDF
                if pdf_path is None:
                    logger.warning("PDF indisponível para: %s", article["title"])
                    continue

                # pula extração se o PDF já foi processado nesta ou em execuções anteriores
                if pdf_path.name in processed_pdfs:
                    logger.info("PDF já processado, pulando extração: %s", pdf_path.name)
                    continue

                # inicializa o parser na primeira vez que for necessário
                if parser is None:
                    logger.info("Carregando modelo spaCy para extração...")
                    parser = Parser()

                if already_downloaded:
                    logger.info("PDF já baixado, iniciando extração: %s", pdf_path.name)
                else:
                    logger.info("PDF baixado agora, iniciando extração: %s", pdf_path.name)

                try:
                    record = parser.parse_pdf(pdf_path)
                except PaywalledPDFError:
                    logger.warning("PDF ignorado (acesso restrito): %s", pdf_path.name)
                    # marca como processado para não tentar de novo em execuções futuras
                    processed_pdfs.add(pdf_path.name)
                    continue

                writer.writerow(record.to_dict())
                # flush garante que o registro seja gravado mesmo se o pipeline travar
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