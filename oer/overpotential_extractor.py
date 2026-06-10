import re
import logging
from typing import Optional
from . import config
from .logger import get_extractor_overpotential_logger

logger = get_extractor_overpotential_logger()

class OverpotentialMaterialMatcher:
    """
    Associa um valor de overpotential ao material mais provável
    presente na sentença âncora.
    """

    def match(
        self,
        anchor_sentence: str,
        overpotential_mV: Optional[int],
        candidates: list,
    ) -> Optional[str]:
        # sem overpotential ou sem sentença não tem o que associar
        if overpotential_mV is None or not anchor_sentence:
            return None

        # acha as posições no texto onde o valor de overpotential aparece em mV
        # pode ter mais de uma ocorrência (ex: "280 mV and 310 mV")
        value_offsets = self._overpotential_value_offsets(
            anchor_sentence,
            overpotential_mV,
        )

        # se o valor não aparece na sentença, não tem como associar ao material
        if not value_offsets:
            logger.debug("Valor %s mV não encontrado na sentença âncora", overpotential_mV)
            return None

        # caso especial: "respectively" indica que vários materiais e valores
        # estão listados em ordem, ex: "Mat1 and Mat2 showed 280 and 310 mV, respectively"
        # nesse caso a associação é posicional, não por distância
        if "respectively" in anchor_sentence.casefold():
            logger.debug("Sentença contém 'respectively' — tentando associação posicional")
            mapped = self._respectively_candidate(
                candidates,
                anchor_sentence,
                overpotential_mV,
            )
            # se conseguiu mapear pelo respectively, retorna direto
            # senão cai no método de distância abaixo
            if mapped:
                logger.info("Material associado via 'respectively': %r", mapped)
                return mapped
            logger.debug("Associação por 'respectively' falhou, usando distância")

        # estratégia principal: associa o material ao valor pelo menor distância no texto
        # a ideia é que o material mencionado mais perto do valor em mV é o mais provável
        best = None
        for value_offset in value_offsets:
            for candidate in candidates:
                # posição do fim do texto do candidato no texto
                candidate_end = (
                    candidate.start +
                    len(candidate.text)
                )

                # material antes do valor: distância é do fim do material até o valor
                # ex: "NiFe (280 mV)" — distância pequena, boa associação
                if candidate.start <= value_offset:
                    distance = value_offset - candidate_end

                # material depois do valor: distância real + penalidade de 120
                # porque material após o valor é menos comum em artigos científicos
                # ex: "an overpotential of 280 mV was achieved by NiFe"
                else:
                    distance = (
                        candidate.start -
                        value_offset +
                        120
                    )

                score = distance

                # penaliza frases genéricas que não são o material principal
                # ex: "the catalyst", "this material", "the electrode"
                if self._is_generic_material_phrase(candidate.text):
                    score += 80

                # mantém o candidato de menor score (menor distância + penalidades)
                if best is None or score < best[0]:
                    best = (score, candidate.text)

        if best:
            logger.info(
                "Material associado por distância: %r (score=%d)",
                best[1],
                best[0],
            )
        else:
            logger.warning(
                "Nenhum material associado ao overpotential de %s mV",
                overpotential_mV,
            )

        return best[1] if best else None

    def _overpotential_value_offsets(
        self,
        source_text: str,
        overpotential_mV: int,
    ) -> list[int]:
        offsets = []

        # padrão para capturar valores em mV, incluindo múltiplos separados por /
        # ex: "280 mV", "280/310 mV"
        pattern = (
            r"(\d+(?:\.\d+)?"
            r"(?:\s*/\s*\d+(?:\.\d+)?)*)"
            r"\s*mV"
        )

        for match in re.finditer(pattern, source_text, re.I):
            # itera sobre cada valor individual dentro do grupo capturado
            # necessário para casos como "280/310 mV" onde há múltiplos valores
            for value_match in re.finditer(
                r"\d+(?:\.\d+)?",
                match.group(1),
            ):
                value = float(value_match.group(0))

                # compara arredondando para int, porque o overpotential_mV é sempre inteiro
                # e o texto pode ter casas decimais como "280.0 mV"
                if int(round(value)) == overpotential_mV:
                    # guarda a posição absoluta do valor no texto original
                    # somando o início do match com o início do valor dentro do grupo
                    offsets.append(
                        match.start(1)
                        + value_match.start()
                    )

        logger.debug(
            "Offsets encontrados para %s mV: %s",
            overpotential_mV,
            offsets,
        )
        return offsets

    def _respectively_candidate(
        self,
        candidates: list,
        source_text: str,
        overpotential_mV: int,
    ) -> Optional[str]:
        # coleta todos os valores em mV da sentença em ordem de aparição
        # ex: "280 and 310 mV" → [280.0, 310.0]
        values = []
        pattern = (
            r"(\d+(?:\.\d+)?"
            r"(?:\s*/\s*\d+(?:\.\d+)?)*"
            r")\s*mV"
        )
        for match in re.finditer(pattern, source_text, re.I):
            # split por / para lidar com "280/310 mV"
            values.extend(
                float(value.strip())
                for value in match.group(1).split("/")
            )

        # precisa de pelo menos 2 candidatos e 2 valores para fazer associação posicional
        # com apenas 1 de cada, o "respectively" não faz sentido
        if len(candidates) < 2:
            logger.debug("Respectively: menos de 2 candidatos, associação posicional impossível")
            return None
        if len(values) < 2:
            logger.debug("Respectively: menos de 2 valores em mV, associação posicional impossível")
            return None

        # associa por índice: o primeiro valor ao primeiro candidato, segundo ao segundo, etc
        # assume que a ordem de aparição dos materiais corresponde à ordem dos valores
        for index, value in enumerate(values):
            if (
                int(round(value))
                == overpotential_mV
                and index < len(candidates)
            ):
                return candidates[index].text

        return None

    def _is_generic_material_phrase(
        self,
        candidate: str,
    ) -> bool:
        # confere se o candidato é uma frase genérica que não identifica um material específico
        # a lista GENERIC_MATERIAL_PHRASES no config guarda esses casos
        # ex: "the catalyst", "this material", "metal oxide"
        return candidate.casefold() in config.GENERIC_MATERIAL_PHRASES