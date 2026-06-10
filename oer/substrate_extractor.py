from typing import Optional

import spacy
from spacy.language import Language
from spacy.matcher import PhraseMatcher

from . import config
from .logger import get_extractor_substrate_logger

logger = get_extractor_substrate_logger()


class SubstrateExtractor:

    def __init__(self, nlp: Optional[Language] = None) -> None:
        # garante a chegada do modelo mesmo que falhe
        # para garantir que não quebre o código, que há possibilidade
        self.nlp = nlp or spacy.load(config.SPACY_MODEL)
        # para "treinar" o matcher com um novo tipo de padrões, pre definidos
        self.matcher = PhraseMatcher(self.nlp.vocab, attr="LOWER")
        # vai ser só para guardar em forma de "lista" todos os que estão dentro de
        # patterns como padrão de substrates, porque dentro de uma chave tem vários padrões
        # só que nesse vamos ter todos os padrões como chave, e os normalized como valor que é chave principal no config
        self.alias_to_normalized = {}
        self._build_matcher()
        self._build_entity_ruler()
        logger.debug(
            "SubstrateExtractor inicializado com %d padrões",
            len(self.alias_to_normalized),
        )

    def _build_matcher(self) -> None:
        # vai ser a lista de padrões do config, com o nlp
        patterns = []
        # aqui o normalized é o tipo do substrate, e o alias é os tipos que ele pode ser referenciado
        # é muito dado por conta que o substrate patterns é em formato de dicionário
        for normalized, aliases in config.SUBSTRATE_PATTERNS.items():
            # o alias padroniza o nome, uma vez que o dicionario dos padrões está dado em uma forma que sua referencia guarda todos
            # aqui vão ser listados todos e vai ser referenciado o principal, uma troca de valores vamos dizer assim
            # melhor para atribuição e retorno para identificação
            for alias in aliases:
                self.alias_to_normalized[alias] = normalized
                # coloca os nomes nos padrões para colocar no matcher
                # o doc é uma representação de um texto em forma de texto para o spacy
                patterns.append(self.nlp.make_doc(alias))
        # adciona o padrão ao matcher que o modelo vai conseguir ler e usar
        self.matcher.add("SUBSTRATE", patterns)
        # era algo que o matcher não tinha antes desse padrão de substrates, e iria falhar para pegar ele
        # mas com isso, coloquei esse padrão de substrates, para conseguir pegar os substratos
        # se tiver novos vai precisar ser adcionado manualmente no config

    def _build_entity_ruler(self) -> None:
        # agora precisamos dizer o que é esse padrão novo que colocamos para ele identificar
        # basicamente como se fosse a entidade, mas uma entidade que vamos identificar
        # não mais algo que ele vai trazer da própria ideia dele, mas sem do que colocamos no matcher

        # verifica se já tem o entity_ruler no modelo e remove ele
        # e adiciona o entity_ruler no lugar, antes do ner
        # porque ele já vem com um entity_ruler mas não é o que a gente quer
        if "entity_ruler" in self.nlp.pipe_names:
            self.nlp.remove_pipe("entity_ruler")
        # definição do entity_ruler, que vai ser o que vai identificar os substrates
        # ele é definido antes do ner, porque ele é uma entidade que vai ser identificada
        ruler = self.nlp.add_pipe("entity_ruler", before="ner")
        # vai adicionar os padrões para o entity_ruler
        patterns = []
        # mesma coisa praticamente do matcher, só que agora ele vai retornar uma entidade
        # em vez de retornar um padrão que vai precisar ser interpretado
        # e ai precisamos definir isso, qual entidade ele vai retornar, baseado em que padrão de id que é normalizado
        # o normalizado é a chave do dicionário de substrates patterns no config, o principal por sua vez
        for normalized, aliases in config.SUBSTRATE_PATTERNS.items():
            for alias in aliases:
                patterns.append({"label": "SUBSTRATE", "pattern": alias, "id": normalized})
        # adiciona os padrões ao entity_ruler que vai conseguir identificar os substrates
        # e ai quando for retornar, vai retornar a entidade identificada
        ruler.add_patterns(patterns)

    def extract(self, text: Optional[str]) -> Optional[str]:
        # para extrair, ele receber o texto, vai ser o abstract ou a introdução
        if not text:
            return None

        # aqui pega o nlp que definimos no init
        # e aplica no texto que vai ser extraido
        # cria todo tokenizado e tbm com as entidades ja definidas
        doc = self.nlp(text)

        # ele vai olhar se ja tem uma entidade com o nome substrate
        # que foi a label definida no substrato do entity ruler
        # ele só procura se já tem aquela entidade no texto
        for ent in doc.ents:
            if ent.label_ == "SUBSTRATE":
                # e retorna o id da entidade definido tbm no entity ruler
                # a ideia é que ele esteja no id, se não tiver ele vai buscar no alias que tem todos
                # e foi definido no mathcer com todos de um nova forma de dicionario, pegados dos patterns do config
                # os patterns são basicamente os aliases
                result = ent.ent_id_ or self.alias_to_normalized.get(ent.text.lower())
                logger.info("Substrato encontrado via entity_ruler: %r → %r", ent.text, result)
                return result

        # aqui ele aplica o mathcer, para ver se consegue encontrar algum
        # ai é o funcionamento de padrão real, não da entidade
        # aplicados nos tokens
        # só chega aqui se ele não encontrar direto as entidades
        matches = self.matcher(doc)
        if not matches:
            logger.warning("Substrato não encontrado no texto")
            return None

        # aqui vai retornar aonde começou e terminou aquele padrão que ele encontrou
        _, start, end = matches[0]
        # depois disso, ele coloca o doc[start, end] que é a forma que nlp retorna
        # e transforma de volta em texto, porque temos um tipo de tokenizer
        # então depois de ter o texto, só confere no dicionario
        matched_text = doc[start:end].text.lower()
        result = self.alias_to_normalized.get(matched_text)
        logger.info("Substrato encontrado via PhraseMatcher: %r → %r", matched_text, result)
        return result