import re
from dataclasses import dataclass
from typing import Dict, Optional, Tuple

from . import config
from .logger import get_extractor_anchor_logger

logger = get_extractor_anchor_logger()


@dataclass
class _PerformanceCandidate:
    overpotential_mV: Optional[int]
    current_density: float
    potential_V: Optional[float]
    sentence: str
    source: str
    method: str

    @property
    def rank(self) -> tuple:
        # quanto mais perto de 10 mA cm⁻², melhor — distância zero ganha rank 0
        cd_distance = abs(self.current_density - AnchorExtractor.STANDARD_CURRENT_DENSITY)
        cd_rank = 0 if cd_distance < 1e-6 else 1

        # body tem prioridade sobre abstract, porque o abstract pode arredondar valores
        source_rank = 0 if self.source == "body" else 1

        # pair é o mais confiável (par direto), depois anchor, depois potential_v
        method_rank = {"pair": 0, "anchor": 1, "potential_v": 2}.get(self.method, 3)

        return (cd_rank, cd_distance, source_rank, method_rank)


class AnchorExtractor:
    """Extract overpotential/current-density pairs from body text and abstract."""

    STANDARD_CURRENT_DENSITY = 10.0

    def extract(
        self,
        full_text: Optional[str],
        abstract: Optional[str] = None,
    ) -> Dict[str, object]:
        candidates: list[_PerformanceCandidate] = []

        # busca primeiro no corpo do artigo, depois no abstract
        # o corpo tem prioridade no rank, mas os dois são pesquisados
        if full_text:
            candidates.extend(self._search_text(full_text, "body"))
        if abstract:
            candidates.extend(self._search_text(abstract, "abstract"))

        if not candidates:
            logger.warning("Nenhum par de desempenho encontrado")
            return self._empty_result()

        # seleciona o melhor candidato pelo rank — menor rank é melhor
        best = min(candidates, key=lambda item: item.rank)
        logger.info(
            "Melhor candidato: overpotential=%s mV | current_density=%s | source=%s | method=%s",
            best.overpotential_mV,
            best.current_density,
            best.source,
            best.method,
        )

        return {
            "overpotential_mV": best.overpotential_mV,
            "current_density": self._format_current_density(best.current_density),
            "potential_V": best.potential_V,
            "performance_source": best.source,
            "anchor_found": True,
            "anchor_sentence": best.sentence,
        }

    def _search_text(self, text: str, source: str) -> list[_PerformanceCandidate]:
        # roda as três estratégias de busca em ordem crescente de confiabilidade
        # pair é o mais direto, potential_v é o mais indireto
        candidates: list[_PerformanceCandidate] = []
        candidates.extend(self._search_direct_pairs(text, source))
        candidates.extend(self._search_potential_vs_rhe(text, source))
        candidates.extend(self._search_anchor_pairs(text, source))
        logger.debug("Candidatos encontrados em '%s': %d", source, len(candidates))
        return candidates

    def _search_direct_pairs(self, text: str, source: str) -> list[_PerformanceCandidate]:
        # busca pares diretos no formato "280 mV at 10 mA cm⁻²"
        # é a estratégia mais confiável porque o par está explícito na mesma frase
        candidates = []
        for match in config.PERFORMANCE_PAIR_PATTERN.finditer(text):
            # rejeita se o valor em mV for na verdade um Tafel slope (ex: "107 mV dec⁻¹")
            if self._looks_like_tafel_slope(text, match.end("overpotential") + 2):
                continue

            current_density = self._normalize_current_density(
                float(match.group("current_density")),
                match.group("current_unit"),
            )
            overpotential_mV = int(round(float(match.group("overpotential"))))

            # faixa realista de overpotential para OER — valores fora disso são ruído
            if not (50 <= overpotential_mV <= 1200):
                continue

            context, _ = self._window(text, match.start(), match.end())
            candidates.append(
                _PerformanceCandidate(
                    overpotential_mV=overpotential_mV,
                    current_density=current_density,
                    potential_V=None,
                    sentence=self._extract_sentence(context),
                    source=source,
                    method="pair",
                )
            )
        return candidates

    def _search_potential_vs_rhe(self, text: str, source: str) -> list[_PerformanceCandidate]:
        # busca potencial absoluto vs RHE e converte para overpotential
        # ex: "1.66 V vs. RHE at 10 mA cm⁻²" → overpotential = (1.66 - 1.23) * 1000 = 430 mV
        # só aceita se houver menção a "overpotential" no prefixo, para evitar falso-positivo
        candidates = []
        for match in config.POTENTIAL_VS_RHE_PATTERN.finditer(text):
            context_start = max(0, match.start() - 80)
            prefix = text[context_start:match.start()].casefold()

            # exige que o contexto anterior mencione overpotential
            # para não confundir com potencial de onset ou potencial de equilíbrio
            if "overpotential" not in prefix and "over-potential" not in prefix:
                continue

            potential_V = float(match.group("potential"))

            # faixa realista de potencial vs RHE para OER
            if not (1.3 <= potential_V <= 2.5):
                continue

            current_density = self._normalize_current_density(
                float(match.group("current_density")),
                match.group("current_unit"),
            )
            overpotential_mV = self._potential_to_overpotential_mV(potential_V)

            # confere também o overpotential convertido
            if not (50 <= overpotential_mV <= 1200):
                continue

            context, _ = self._window(text, match.start(), match.end())
            candidates.append(
                _PerformanceCandidate(
                    overpotential_mV=overpotential_mV,
                    current_density=current_density,
                    potential_V=round(potential_V, 3),
                    sentence=self._extract_sentence(context),
                    source=source,
                    method="potential_v",
                )
            )
        return candidates

    def _search_anchor_pairs(self, text: str, source: str) -> list[_PerformanceCandidate]:
        # busca pela âncora de corrente (ex: "10 mA cm⁻²") e procura o overpotential próximo
        # é menos confiável que pair porque o par não está explícito na mesma expressão
        candidates = []
        for match in config.ANCHOR_PATTERN.finditer(text):
            current_density = self._current_density_from_match(match)
            if current_density is None:
                continue

            context, anchor_offset = self._window(text, match.start(), match.end())

            # procura o valor de overpotential mais próximo da âncora dentro da janela
            overpotential = self._find_overpotential(context, anchor_offset)
            if overpotential is None:
                continue

            _, value = overpotential
            sentence = self._extract_sentence(context)

            # rejeita se a sentença não tiver nenhum sinal de desempenho eletroquímico
            # evita pegar janelas de contexto que não são sobre resultados
            if not self._sentence_contains_performance(sentence):
                continue

            candidates.append(
                _PerformanceCandidate(
                    overpotential_mV=int(round(value)),
                    current_density=current_density,
                    potential_V=None,
                    sentence=sentence,
                    source=source,
                    method="anchor",
                )
            )
        return candidates

    def _potential_to_overpotential_mV(self, potential_v: float) -> int:
        # converte potencial absoluto vs RHE para overpotential em mV
        # subtrai o potencial de equilíbrio da OER (1.23 V) e converte para mV
        return int(round((potential_v - config.RHE_REFERENCE_V) * 1000))

    def _normalize_current_density(self, value: float, unit: str) -> float:
        # converte A cm⁻² para mA cm⁻² quando necessário
        # o padrão interno é sempre mA cm⁻²
        if unit.casefold() == "a":
            return value * 1000
        return value

    def _current_density_from_match(self, match: re.Match) -> Optional[float]:
        # tenta extrair a densidade de corrente do match em diferentes formatos
        # cada grupo cobre uma variante sintática diferente do padrão de âncora

        # formato com η subscrito numérico (ex: "η₁₀")
        eta_cd = match.groupdict().get("eta_current_density")
        if eta_cd is not None:
            return float(eta_cd)

        # formato com subscrito unicode (ex: "j₁₀") — converte para ASCII antes
        eta_sub = match.groupdict().get("eta_sub")
        if eta_sub:
            subscript_map = str.maketrans("₀₁₂₃₄₅₆₇₈₉", "0123456789")
            digits = eta_sub.translate(subscript_map)
            if digits:
                return float(digits)

        # formatos convencionais com valor e unidade explícitos
        for cd_key, unit_key in [("current_density", "current_unit"), ("current_density3", "current_unit3")]:
            value = match.groupdict().get(cd_key)
            unit = match.groupdict().get(unit_key)
            if value is not None and unit is not None:
                return self._normalize_current_density(float(value), unit)

        return None

    def _format_current_density(self, current_density: float) -> int | float:
        # retorna inteiro se for valor redondo (ex: 10.0 → 10), float caso contrário
        # mantém a leitura limpa no CSV para os casos mais comuns
        rounded = round(current_density)
        if abs(current_density - rounded) < 1e-6:
            return int(rounded)
        return round(current_density, 3)

    def _window(self, text: str, start: int, end: int) -> Tuple[str, int]:
        # extrai uma janela de contexto ao redor do match
        # retorna o texto da janela e o offset do match dentro dela
        left = max(0, start - config.ANCHOR_CONTEXT_CHARS)
        right = min(len(text), end + config.ANCHOR_CONTEXT_CHARS)
        return text[left:right], start - left

    def _find_overpotential(self, context: str, anchor_offset: int) -> Optional[Tuple[int, float]]:
        # procura valores de overpotential na janela de contexto
        # rejeita Tafel slopes e diferenças de potencial que não são overpotential
        # retorna o candidato mais próximo da âncora de corrente
        candidates = []
        for match in config.OVERPOTENTIAL_PATTERN.finditer(context):
            # rejeita se o valor for um Tafel slope (ex: "107 mV dec⁻¹")
            if self._looks_like_tafel_slope(context, match.end()):
                continue
            # rejeita se o valor for uma diferença relativa (ex: "230 mV lower than")
            if self._looks_like_difference(context, match.start()):
                continue
            value = float(match.group(1))
            if 50 <= value <= 1200 and self._has_overpotential_signal(context, match.start(), anchor_offset):
                candidates.append((abs(match.start() - anchor_offset), value))
        if not candidates:
            return None
        # ordena por distância e retorna o mais próximo
        candidates.sort(key=lambda item: item[0])
        return candidates[0]

    def _looks_like_difference(self, context: str, value_start: int) -> bool:
        # detecta quando o valor em mV é uma diferença relativa e não um overpotential absoluto
        # ex: "230 mV lower than CF-O" não é o overpotential do catalisador
        prefix = context[max(0, value_start - 60):value_start].casefold()
        suffix = context[value_start:value_start + 30].casefold()
        difference_signals = (
            "lower than",
            "higher than",
            "less than",
            "more than",
            "reduction of",
            "decrease of",
            "increase of",
            "smaller than",
            "difference of",
            "improvement of",
        )
        return any(signal in prefix or signal in suffix for signal in difference_signals)

    def _looks_like_tafel_slope(self, context: str, value_end: int) -> bool:
        # detecta Tafel slopes que têm o mesmo formato numérico mas não são overpotential
        # ex: "107.52 mV dec⁻¹" — o "dec" logo após o valor é o sinal
        tail = context[value_end:value_end + 25].casefold()
        return bool(re.match(r"\s*(?:dec|decade|dec\s*[-−–]\s*1|dec[-−–]?1)", tail))

    def _has_overpotential_signal(self, context: str, value_start: int, anchor_offset: int) -> bool:
        # verifica se há algum termo que indique que o valor é realmente um overpotential
        # analisa a região entre o valor e a âncora de corrente mais um buffer
        left = max(0, min(value_start, anchor_offset) - 140)
        right = min(len(context), max(value_start, anchor_offset) + 140)
        nearby = context[left:right].casefold()

        # cell voltage e voltage gap são termos de célula completa, não de eletrodo
        # só aceita se também mencionar overpotential explicitamente
        if any(term in nearby for term in ("cell voltage", "voltage gap", "cell-voltage")):
            return "overpotential" in nearby or "η" in nearby or "eta" in nearby

        # qualquer um desses termos é suficiente para confirmar que é overpotential
        return (
            "overpotential" in nearby
            or "over-potential" in nearby
            or "η" in nearby
            or "eta" in nearby
            or "mv" in nearby
            or "\u207b" in nearby
            or ("potential" in nearby and "vs" in nearby)
            or ("onset" in nearby and "potential" in nearby)
        )

    def _extract_sentence(self, context: str) -> str:
        # limpa espaços e divide em sentenças pelo ponto final
        # retorna a sentença que contém o padrão de desempenho
        # inclui a sentença anterior para dar contexto (ex: quem é o catalisador)
        cleaned = " ".join(context.split())
        sentences = re.split(r"(?<=[.!?])\s+", cleaned)
        for index, sentence in enumerate(sentences):
            if (
                config.ANCHOR_PATTERN.search(sentence)
                or config.OVERPOTENTIAL_PATTERN.search(sentence)
                or config.PERFORMANCE_PAIR_PATTERN.search(sentence)
                or config.POTENTIAL_VS_RHE_PATTERN.search(sentence)
            ):
                # inclui a sentença anterior se existir — frequentemente menciona o material
                previous = sentences[index - 1] if index > 0 else ""
                return f"{previous} {sentence}".strip()
        return cleaned

    def _sentence_contains_performance(self, sentence: str) -> bool:
        # confirma que a sentença extraída tem pelo menos um sinal de desempenho
        # evita retornar sentenças de contexto que não têm dados eletroquímicos
        return bool(
            config.OVERPOTENTIAL_PATTERN.search(sentence)
            or config.PERFORMANCE_PAIR_PATTERN.search(sentence)
            or "η" in sentence
            or "eta" in sentence.casefold()
        )

    def _empty_result(self) -> Dict[str, object]:
        # retorna o resultado padrão quando nenhum par de desempenho é encontrado
        # anchor_found=False sinaliza para o parser que não houve extração
        return {
            "overpotential_mV": None,
            "current_density": None,
            "potential_V": None,
            "performance_source": None,
            "anchor_found": False,
            "anchor_sentence": None,
        }