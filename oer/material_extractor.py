import re
import logging
from dataclasses import dataclass
from typing import Optional
from . import config
from .overpotential_extractor import OverpotentialMaterialMatcher
from .logger import get_extractor_logger

logger = get_extractor_logger()

@dataclass
class _Candidate:
    text: str
    source_name: str
    source_text: str
    start: int

class MaterialExtractor:
    # extrator determinístico: usa regex e heurísticas de score para identificar
    # o material catalítico do artigo, sem depender de modelos de linguagem
    def __init__(self) -> None:
        # aqui é a definição de palavras que não queremos que sejam consideradas
        # só fui definindo algumas normalmente, e outras como teste e erro
        # que estavam sendo retornadas de forma erroneia
        self.stopwords = {s.casefold() for s in config.MATERIAL_DOMAIN_STOPWORDS}
        self.overpotential_matcher = OverpotentialMaterialMatcher()
        logger.debug("MaterialExtractor inicializado")

    def extract(
        self,
        title: Optional[str],
        abstract: Optional[str],
        anchor_sentence: Optional[str],
        overpotential_mV: Optional[int] = None,
    ) -> Optional[str]:
        logger.debug(
            "Iniciando extração | overpotential_mV=%s | anchor=%s",
            overpotential_mV,
            bool(anchor_sentence),
        )

        # da onde vem meus conteudos principais de extração
        # a ordem importa: âncora tem mais peso no score, abstract vem depois, título por último
        sources = [
            ("anchor_sentence", anchor_sentence or ""),
            ("abstract", abstract or ""),
            ("title", title or ""),
        ]

        # aqui usa a função de coleta para coletar os candidatos
        # vai listar todas, porque aqui não seleciona o melhor, só vai listar todos os candidatos
        candidates = self._collect_candidates(sources)
        logger.info("Candidatos coletados: %d", len(candidates))

        # aqui é para o sobrepotencial, se ele não for nulo e tiver sentença âncora
        # ele vai listar tbm todos os candidatos que estão na sentença âncora
        # a ideia é tentar associar o valor de overpotential diretamente ao material mencionado
        # na mesma sentença, o que é mais preciso do que só pegar o melhor score geral
        if overpotential_mV is not None and anchor_sentence:
            anchor_candidates = [
                candidate
                for candidate in candidates
                if candidate.source_name == "anchor_sentence"
            ]
            # aqui é a chamada da função do sobrepotencial, vai para outro modulo py
            # para rodar e ver se consegue associar o sobrepotencial ao material
            matched = self.overpotential_matcher.match(
                self._normalize_text(anchor_sentence),
                overpotential_mV,
                anchor_candidates,
            )
            # se ele conseguir associar o sobrepotencial ao material, ele retorna o material
            # esse é o caminho mais confiável, por isso retorna direto sem continuar
            if matched:
                logger.info("Material encontrado via overpotential matcher: %r", matched)
                return matched
            logger.debug("Overpotential matcher não encontrou correspondência")

        # aqui é para o melhor candidato, se o overpotential matcher não conseguiu associar
        # percorre todos os candidatos coletados e retorna o de maior score
        best_candidate = self._best_candidate(candidates)

        # se ele conseguir encontrar o melhor candidato, ele retorna o melhor candidato
        if best_candidate:
            logger.info("Melhor candidato selecionado: %r", best_candidate)
            return best_candidate

        # se não encontrou nenhum candidato válido em nenhuma das fontes, retorna None
        # isso indica que o artigo provavelmente não tem fórmula química identificável
        # ou que todos os candidatos foram filtrados pelo _is_valid_candidate
        logger.warning("Extração sem resultado para title=%r", title)
        return None

    def _collect_candidates(
        self,
        # vai ser uma tupla, da onde tirou o candidato e o proprio candidato
        sources: list[tuple[str, str]],
    ) -> list[_Candidate]:
        # percorre cada fonte, normaliza o texto e roda o extrator de fórmulas
        # só adiciona à lista se passar pela validação do _is_valid_candidate
        candidates = []
        for source_name, source_text in sources:
            source_text = self._normalize_text(source_text)
            # pula fonte vazia para não rodar regex em string vazia
            if not source_text:
                continue
            for candidate in self._formula_candidates(source_name, source_text):
                # filtra candidatos inválidos antes de adicionar à lista
                if not self._is_valid_candidate(candidate.text):
                    continue
                candidates.append(candidate)
        return candidates

    def _best_candidate(
        self,
        candidates: list[_Candidate],
    ) -> Optional[str]:
        # percorre todos os candidatos e mantém o de maior score
        # se a lista estiver vazia, retorna None
        best_candidate = None
        best_score = -1
        for candidate in candidates:
            # aqui é a chamada da função de score para scorear o candidato
            # é a principal função para decisão e retorno tbm do melhor candidato
            score = self._score_candidate(candidate)
            # atualiza o melhor só se o score atual for maior que o anterior
            if score > best_score:
                best_score = score
                best_candidate = candidate.text
        if best_candidate:
            logger.debug("Melhor candidato: %r (score=%d)", best_candidate, best_score)
        return best_candidate

    def _formula_candidates(self, source_name: str, source_text: str) -> list[_Candidate]:
        # usa o COMPOUND_PATTERN do config para achar matches de fórmulas químicas no texto
        # para cada match, tenta expandir com descritores adjacentes (ex: "NiFe LDH nanosheet")
        # só adiciona se o base realmente parecer uma fórmula química
        candidates = []
        for match in config.COMPOUND_PATTERN.finditer(source_text):
            base = self._clean_candidate(match.group(0))
            # rejeita o match se não parecer fórmula química de verdade
            if not self._looks_like_formula(base):
                continue
            # tenta expandir o candidato com palavras descritoras que vêm logo depois
            expanded = self._expand_descriptor(source_text, match.end(), base)
            candidates.append(_Candidate(expanded, source_name, source_text, match.start()))
        return candidates

    def _expand_descriptor(self, source_text: str, end: int, base: str) -> str:
        # tenta estender o candidato com palavras descritoras que vêm logo depois da fórmula
        # ex: "NiFeOx" + "nanosheet" → "NiFeOx nanosheet"
        words = [base]
        tail = source_text[end:].lstrip()
        while tail and len(" ".join(words)) < 90:
            # para quando encontra separador forte (vírgula, ponto, parêntese)
            if config.MATERIAL_STOP_AFTER_PATTERN.match(tail):
                break
            match = re.match(r"([A-Za-z-]+)", tail)
            # para quando a próxima palavra não é um descritor de material válido
            if not match or not config.MATERIAL_DESCRIPTOR_PATTERN.match(match.group(1)):
                break
            words.append(match.group(1))
            # avança o tail pulando espaços e separadores leves
            tail = tail[match.end():].lstrip(" ,;:-")
        return self._clean_candidate(" ".join(words))

    def _normalize_text(self, text: str) -> str:
        # troca espaço não-separável (unicode) por espaço normal
        text = text.replace("\u00a0", " ")
        # remove espaços ao redor de / e @ que o PDF às vezes insere (ex: "NiFe / C" → "NiFe/C")
        text = re.sub(r"\s+([/@])\s+", r"\1", text)
        # reconecta hifens quebrados entre linhas no PDF (ex: "nano-\nsheet" → "nano-sheet")
        text = re.sub(r"([A-Za-z0-9])[-−–]\s+([A-Za-z])", r"\1-\2", text)
        # colapsa múltiplos espaços em um só
        return " ".join(text.split())

    def _clean_candidate(self, candidate: str) -> str:
        # colapsa espaços internos extras
        candidate = " ".join(candidate.split())
        # remove espaços ao redor de / e @ (mesmo critério do normalize)
        candidate = re.sub(r"\s+([/@])\s+", r"\1", candidate)
        # normaliza variantes de hífen (−, –) para hífen simples
        candidate = re.sub(r"\s*[-−–]\s*", "-", candidate)
        # tira pontuação solta nas bordas que o regex pode ter capturado junto
        return candidate.strip(".,;:()[]{} ")

    def _is_valid_candidate(self, candidate: str) -> bool:
        candidate_lower = candidate.casefold()

        # muito curto (ruído) ou muito longo (provavelmente pegou texto demais)
        if not candidate or len(candidate) < 3 or len(candidate) > 100:
            return False

        # pipe geralmente vem de tabelas mal extraídas do PDF
        # http indica que pegou uma URL no lugar de um material
        if "|" in candidate or "http" in candidate_lower:
            return False

        # unidades de medida que o regex às vezes confunde com fórmula (ex: "mV", "cm⁻²", "mol")
        if any(unit in candidate_lower for unit in config.MATERIAL_INVALID_UNITS):
            return False

        # palavras genéricas do domínio que não são materiais
        # ex: "electrode", "solution", "water", "current"
        if candidate_lower in self.stopwords or any(stop in candidate_lower for stop in self.stopwords):
            return False

        # siglas puras em maiúsculo que não são materiais (ex: "OER", "HER", "RHE")
        if self._looks_like_plain_acronym(candidate):
            return False

        # exige pelo menos um elemento químico real ou token de material
        # sem isso, provavelmente é texto genérico que passou pelos filtros anteriores
        if not self._has_chemical_signal(candidate):
            return False

        return True

    def _looks_like_plain_acronym(self, candidate: str) -> bool:
        # tira tudo que não é letra para comparar só as letras
        compact = re.sub(r"[^A-Za-z]", "", candidate)

        # sem letras não é sigla; com dígito provavelmente é fórmula (ex: "RuO2")
        if not compact or any(ch.isdigit() for ch in candidate):
            return False

        # hífen, barra ou @ indicam composto ou heteroestrutura, não sigla pura
        if any(sep in candidate for sep in ("-", "/", "@")):
            return False

        # se não for tudo maiúsculo, não é sigla (ex: "NiOx" tem minúsculo)
        if compact.upper() != compact:
            return False

        # se chegou aqui é sigla pura — só deixa passar se estiver na lista de acrônimos
        # de materiais conhecidos que o projeto aceita (ex: "MXene", "MOF")
        return candidate.casefold() not in config.MATERIAL_VALID_ACRONYMS

    def _has_chemical_signal(self, text: str) -> bool:
        text_folded = text.casefold()

        # tokens de domínio que indicam material mesmo sem fórmula
        # ex: "oxide", "hydroxide", "perovskite", "carbide"
        has_material_token = any(
            token in text_folded
            for token in config.MATERIAL_CHEMICAL_TOKENS
        )

        # aceita se tiver estrutura de fórmula OU token de material conhecido
        return self._looks_like_formula(text) or has_material_token

    def _looks_like_formula(self, text: str) -> bool:
        # tira tudo que não é letra para checar se é sigla conhecida
        compact = re.sub(r"[^A-Za-z]", "", text)

        # siglas conhecidas que o regex confunde com fórmula (ex: "OER", "CV", "LSV")
        if compact.upper() in config.EXCLUDED_FORMULA_ACRONYMS:
            return False

        # coleta só os tokens que são elementos químicos reais da tabela periódica
        elements = []
        for token in re.findall(r"[A-Z][a-z]?", text):
            if token in config.CHEMICAL_ELEMENTS:
                elements.append(token)

        # sem nenhum elemento químico real, não é fórmula
        if not elements:
            return False

        # dígito junto de elementos quase certamente é fórmula (ex: "Fe2O3", "NiCoO4")
        if any(ch.isdigit() for ch in text):
            return True

        # sem dígito, exige pelo menos 2 elementos distintos E um padrão de token de fórmula
        # isso evita que palavras como "CoN" (só 1 elemento) passem como fórmula
        return len(set(elements)) >= 2 and bool(config.FORMULA_TOKEN_PATTERN.search(text))

    def _score_candidate(self, candidate: _Candidate) -> int:
        text = candidate.text
        text_lower = text.casefold()
        score = 0

        # fonte: âncora vale mais porque é onde o desempenho foi reportado
        # abstract e título têm peso menor mas ainda são fontes confiáveis
        if candidate.source_name == "anchor_sentence":
            score += 8
        elif candidate.source_name == "abstract":
            score += 5
        elif candidate.source_name == "title":
            score += 4

        # fórmulas com número são mais específicas que palavras soltas (ex: "Fe2O3" > "iron oxide")
        if any(ch.isdigit() for ch in text):
            score += 5

        # separadores indicam compostos mistos ou heteroestruturas (ex: "NiFe/C", "Co@N-C")
        if any(sep in text for sep in ("-", "/", "@")):
            score += 3

        # tokens que costumam acompanhar materiais relevantes no domínio OER
        # ex: "catalyst", "oxide", "nanoparticle", "electrocatalyst"
        if any(token in text_lower for token in config.MATERIAL_SCORE_TOKENS):
            score += 3

        # mais elementos químicos distintos → fórmula mais complexa → mais específica
        score += min(len(set(re.findall(r"[A-Z][a-z]?", text))), 5)

        # candidatos com mais palavras geralmente têm mais contexto descritivo
        # ex: "NiFe LDH nanosheet" é mais informativo que só "NiFe"
        score += min(len(text.split()), 4)

        # bônus de contexto: se o candidato aparece perto de termos de desempenho eletroquímico
        # isso aumenta a chance de ser o material sendo reportado no resultado principal
        nearby = candidate.source_text[max(0, candidate.start - 80): candidate.start + 160].casefold()
        # overpotential, 10 mA e current density são os principais indicadores de resultado OER
        if "overpotential" in nearby or "10 ma" in nearby or "current density" in nearby:
            score += 2
        # catalyst e electrocatalyst confirmam que o contexto é sobre o material ativo
        if "catalyst" in nearby or "electrocatalyst" in nearby:
            score += 1

        return score