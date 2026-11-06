__author__ = 'Pedro Henrique Sousa Pinheiro'
"""Modelo e repositório das curvas características — o equivalente ao
LoadShape do OpenDSS. Uma curva descreve como a carga (ou a geração) varia
ao longo do tempo, sempre em percentual do valor nominal do elemento.

A classificação por 'modo' indica em qual propriedade do OpenDSS a curva
pode ser referenciada:
    - "daily"  -> propriedade 'daily'  (perfil ao longo de 24 horas)
    - "duty"   -> propriedade 'duty'   (ciclo curto, duração configurável)
    - "yearly" -> propriedade 'yearly' (perfil sazonal, por dia do ano)

O armazenamento interno é uniforme: cada ponto é um par (hora, percentual) e
a hora vai sempre em HORAS, independentemente do modo. Esse é o formato que a
propriedade 'hour' de um Loadshape aceita nativamente, o que dispensa
conversão na hora de exportar."""

import os
import json
from dataclasses import dataclass, field, asdict
from typing import List, Tuple, Optional

from .modelo_rede import gerar_nome_unico

NOME_ARQUIVO_CURVAS = "curvas.json"

MODOS_CURVA = ["daily", "duty", "yearly"]


@dataclass
class CurvaCaracteristica:
    nome: str
    natureza: str  # "geracao" ou "carga" (apenas rótulo semântico do eixo %)
    modo: str = "daily"  # "daily" | "duty" | "yearly"
    duracao_minutos: Optional[float] = None  # usado somente quando modo == "duty"
    pontos: List[Tuple[float, float]] = field(default_factory=list)  # (hora, percentual)

    def pontos_ordenados(self):
        return sorted(self.pontos, key=lambda p: p[0])

    def horas(self):
        return [p[0] for p in self.pontos_ordenados()]

    def percentuais(self):
        return [p[1] for p in self.pontos_ordenados()]

    def multiplicadores(self):
        return [p[1] / 100.0 for p in self.pontos_ordenados()]


def _caminho_arquivo(pasta_curvas: str) -> str:
    return os.path.join(pasta_curvas, NOME_ARQUIVO_CURVAS)


def listar_curvas(pasta_curvas: str) -> List[CurvaCaracteristica]:
    caminho = _caminho_arquivo(pasta_curvas)
    # Ausência de arquivo significa projeto ainda sem curvas, não erro:
    # o chamador recebe lista vazia e segue.
    if not os.path.exists(caminho):
        return []

    with open(caminho, "r", encoding="utf-8") as f:
        dados = json.load(f)

    curvas = []
    for d in dados:
        pontos = [tuple(p) for p in d.get("pontos", [])]
        curvas.append(CurvaCaracteristica(
            nome=d["nome"],
            natureza=d.get("natureza", "carga"),
            modo=d.get("modo", "daily"),
            duracao_minutos=d.get("duracao_minutos"),
            pontos=pontos,
        ))
    return curvas


def listar_curvas_por_modo(pasta_curvas: str, modo: str) -> List[CurvaCaracteristica]:
    return [c for c in listar_curvas(pasta_curvas) if c.modo == modo]


def obter_curva(pasta_curvas: str, nome: str) -> Optional[CurvaCaracteristica]:
    for curva in listar_curvas(pasta_curvas):
        if curva.nome == nome:
            return curva
    return None


def _persistir(pasta_curvas: str, curvas: List[CurvaCaracteristica]):
    # Grava o repositório inteiro de uma vez. A lista é pequena (algumas
    # dezenas de curvas), então reescrever tudo custa menos que manter
    # escrita incremental e arriscar arquivo inconsistente.
    os.makedirs(pasta_curvas, exist_ok=True)
    caminho = _caminho_arquivo(pasta_curvas)
    dados = [asdict(c) for c in curvas]
    # ensure_ascii=False mantém os acentos legíveis no JSON — os nomes de
    # curva são escritos pelo usuário em português.
    with open(caminho, "w", encoding="utf-8") as f:
        json.dump(dados, f, indent=2, ensure_ascii=False)


def salvar_nova_curva(pasta_curvas: str, curva: CurvaCaracteristica) -> str:
    """Grava a curva como nova entrada no repositório.

    Nome repetido — em qualquer modo — é renomeado automaticamente, e é esse
    nome final que a função devolve. Quem chama precisa usar o retorno, não o
    nome que passou: os dois podem divergir."""
    curvas = listar_curvas(pasta_curvas)
    nomes_existentes = [c.nome for c in curvas]
    nome_final = gerar_nome_unico(curva.nome, nomes_existentes)
    curva.nome = nome_final

    curvas.append(curva)
    _persistir(pasta_curvas, curvas)
    return nome_final


def atualizar_curva(pasta_curvas: str, curva: CurvaCaracteristica):
    """Substitui a curva de mesmo nome, preservando a posição conceitual
    de edição (o nome é a chave; nada é renomeado aqui)."""
    curvas = listar_curvas(pasta_curvas)
    curvas = [c for c in curvas if c.nome != curva.nome]
    curvas.append(curva)
    _persistir(pasta_curvas, curvas)


def remover_curva(pasta_curvas: str, nome: str):
    curvas = listar_curvas(pasta_curvas)
    curvas = [c for c in curvas if c.nome != nome]
    _persistir(pasta_curvas, curvas)