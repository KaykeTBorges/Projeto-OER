# OER Scientific Extraction Pipeline

Pipeline modular e determinístico para extração de dados de artigos científicos sobre Oxygen Evolution Reaction (OER), sem LLMs.

## Módulos

- `oer/scraper.py`: busca artigos na Nature e baixa PDFs.
- `oer/pdf_reader.py`: extrai `title`, `abstract`, `doi`, `front_text`, `full_text` via PyMuPDF.
- `oer/material_extractor.py`: identifica material catalítico com spaCy e `noun_chunks`.
- `oer/substrate_extractor.py`: extrai e normaliza substrato com `PhraseMatcher` + `EntityRuler`.
- `oer/anchor_extractor.py`: localiza âncora `10 mA cm-2` e sobrepotencial contextual.
- `oer/parser.py`: orquestra o pipeline e gera `OERRecord`.
- `oer/schemas.py`: estrutura tipada do resultado.

## Execução

```bash
uv sync
python -m spacy download en_core_web_sm
uv run oer-pipeline
```

Reprocessar PDFs já presentes no CSV (ex.: após melhorar extração de material):

```bash
uv run oer-pipeline --reprocess
```

Saída: `output/oer_records.csv`.

Logs: `logs/scraper.log`, `logs/pipeline.log`, `logs/parser.log`.
