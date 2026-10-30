__author__ = 'Pedro Henrique Sousa Pinheiro'
"""Model + repositório de Curvas Características (equivalentes ao
LoadShape do OpenDSS): definem o comportamento de um elemento de carga
ou geração ao longo do tempo, em percentual do seu valor nominal.

Cada curva é classificada por 'modo', que corresponde à propriedade do
elemento do OpenDSS onde ela pode ser referenciada:
    - "daily"  -> propriedade 'daily'  (perfil ao longo de 24 horas)
    - "duty"   -> propriedade 'duty'   (ciclo curto, duração configurável)
    - "yearly" -> propriedade 'yearly' (perfil sazonal, por dia do ano)

Internamente, os pontos são sempre armazenados como (hora, percentual),
com 'hora' sempre em HORAS (formato aceito nativamente pela propriedade
'hour' de um Loadshape do OpenDSS, independentemente do modo de uso)."""

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
    os.makedirs(pasta_curvas, exist_ok=True)
    caminho = _caminho_arquivo(pasta_curvas)
    dados = [asdict(c) for c in curvas]
    with open(caminho, "w", encoding="utf-8") as f:
        json.dump(dados, f, indent=2, ensure_ascii=False)


def salvar_nova_curva(pasta_curvas: str, curva: CurvaCaracteristica) -> str:
    """Salva como uma nova curva. Se o nome já existir (em qualquer modo),
    é auto-renomeada. Retorna o nome final."""
    curvas = listar_curvas(pasta_curvas)
    nomes_existentes = [c.nome for c in curvas]
    nome_final = gerar_nome_unico(curva.nome, nomes_existentes)
    curva.nome = nome_final

    curvas.append(curva)
    _persistir(pasta_curvas, curvas)
    return nome_final


def atualizar_curva(pasta_curvas: str, curva: CurvaCaracteristica):
    """Substitui a curva existente de mesmo nome (edição in-place)."""
    curvas = listar_curvas(pasta_curvas)
    curvas = [c for c in curvas if c.nome != curva.nome]
    curvas.append(curva)
    _persistir(pasta_curvas, curvas)


def remover_curva(pasta_curvas: str, nome: str):
    curvas = listar_curvas(pasta_curvas)
    curvas = [c for c in curvas if c.nome != nome]
    _persistir(pasta_curvas, curvas)