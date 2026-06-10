# PIVIC — OER Scientific Extraction Pipeline

Pipeline modular e **determinístico** para extrair dados de artigos científicos sobre **Oxygen Evolution Reaction (OER)** a partir de PDFs. Não usa LLMs: apenas regex, heurísticas e spaCy (SciSpaCy).

## O que o pipeline faz

1. Busca artigos na Nature e baixa PDFs (`scraper`)
2. Lê metadados e texto do PDF (`pdf_reader`)
3. Extrai desempenho eletroquímico, material, substrato e eletrólito (`parser`)
4. Grava um registro por artigo em `output/oer_records.csv`

## Fluxo de extração

```
PDF
 └─ PDFReader          → title, abstract, doi, full_text
 └─ AnchorExtractor    → overpotential_mV, current_density, anchor_sentence
 └─ MaterialExtractor  → material catalítico
 └─ SubstrateExtractor → substrato (eletrodo de suporte)
 └─ Parser             → eletrólito, confidence, extraction_note
 └─ OERRecord → CSV
```

### Desempenho (`anchor_extractor`)

Busca pares **overpotential + densidade de corrente** no corpo do artigo e no abstract, com prioridade para **10 mA cm⁻²**.

Estratégias (em ordem de preferência entre candidatos):

- par direto (`280 mV at 10 mA cm⁻²`)
- potencial vs RHE no abstract (`1.66 V vs. RHE at 10 mA cm⁻²` → `potential_V` + η convertido)
- âncora clássica (`10 mA cm⁻²` + mV próximo na janela de contexto)

Campos relacionados:

| Campo | Descrição |
|---|---|
| `overpotential_mV` | Sobrepotencial em mV |
| `current_density` | Densidade de corrente (mA cm⁻²) |
| `potential_V` | Potencial total vs RHE, quando aplicável |
| `performance_source` | `"body"` ou `"abstract"` |
| `anchor_found` | Se algum par válido foi encontrado |
| `anchor_sentence` | Sentença usada na extração |

### Material (`material_extractor` + `overpotential_extractor`)

1. Coleta candidatos de fórmula/química (regex) em âncora, abstract e título
2. Se há âncora e overpotential, o **`OverpotentialMaterialMatcher`** escolhe qual candidato corresponde ao valor em mV
3. Senão, pontua os candidatos (âncora > abstract > título)
4. Se nenhum candidato válido for encontrado, retorna `None`

### Substrato (`substrate_extractor`)

Lista fechada de padrões em `config.SUBSTRATE_PATTERNS`, identificados com **PhraseMatcher** + **EntityRuler** no SciSpaCy.

## Módulos

| Arquivo | Função |
|---|---|
| `oer/main.py` | CLI: scrape + extract → CSV |
| `oer/scraper.py` | Busca Nature, download de PDFs |
| `oer/pdf_reader.py` | Extração de texto com PyMuPDF |
| `oer/anchor_extractor.py` | Overpotential e corrente (corpo + abstract) |
| `oer/material_extractor.py` | Material catalítico (regex + scoring) |
| `oer/overpotential_extractor.py` | Associa overpotential ao material na sentença âncora |
| `oer/substrate_extractor.py` | Substrato normalizado |
| `oer/parser.py` | Orquestração do pipeline |
| `oer/schemas.py` | `OERRecord` (dataclass de saída) |
| `oer/config.py` | Padrões regex, listas de substrato/stopwords, constantes |

## Instalação

Requer Python ≥ 3.11. O modelo spaCy científico (`en_core_sci_lg`) já está declarado no `pyproject.toml`.

```bash
uv sync
```

## Execução

```bash
uv run oer-pipeline
```

Reprocessar PDFs que já constam no CSV (útil após mudanças nos extractors):

```bash
uv run oer-pipeline --reprocess
```

## Saída

**CSV:** `output/oer_records.csv`

**PDFs baixados:** `pdfs/`

**Logs:** `logs/scraper.log`, `logs/pipeline.log`, `logs/parser.log`

### Colunas do CSV

`doi`, `source_pdf`, `title`, `abstract`, `material`, `substrate`, `electrolyte`, `overpotential_mV`, `current_density`, `potential_V`, `performance_source`, `confidence`, `extraction_note`, `anchor_found`, `anchor_sentence`

### Valores de `extraction_note`

| Valor | Significado |
|---|---|
| `complete` | Material + âncora + overpotential (@10 mA) |
| `nonstandard_current_density` | Completo, mas corrente ≠ 10 mA cm⁻² |
| `anchor_missing_material` | Desempenho encontrado, material não |
| `material_without_anchor` | Material encontrado, sem par de desempenho |
| `missing_anchor` | Sinal OER no texto, sem extração de desempenho |
| `no_oer_signal` | Texto sem indício claro de OER |

## Configuração

Parâmetros centralizados em `oer/config.py`: query de busca, padrões de âncora/overpotential, listas de substrato, stopwords de material, elementos químicos e regex de fórmulas.
