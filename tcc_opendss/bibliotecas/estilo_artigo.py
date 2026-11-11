__author__ = 'Pedro Henrique Sousa Pinheiro'
"""Estilo visual das figuras do artigo (TCC) — fonte única.

Este módulo permite REPRODUZIR, nos gráficos exportados pela ferramenta,
exatamente o estilo das figuras do artigo: a paleta Okabe-Ito (segura para
daltônicos e para impressão em preto e branco), uma cor e UM marcador por
dia da semana, e marcas a cada duas horas — o equivalente ao
``mark repeat=2`` do pgfplots usado no LaTeX.

As constantes espelham os ``\\definecolor`` do preâmbulo de
``conference_101719.tex`` (corCarga, corCargaBESS, corImport, corFV,
corDescBESS, corSeg…corDom). Se a paleta do artigo mudar, mude AQUI.

Sem dependência de matplotlib nem de PySide6: apenas constantes e funções
puras, importáveis de qualquer camada (inclui testes headless).
"""

import unicodedata
from typing import Optional

# Ordem canônica dos dias (índice 0 = segunda), alinhada ao índice ``dia``
# do ledger da simulação ao vivo.
DIAS_NOMES = ("Segunda", "Terça", "Quarta", "Quinta", "Sexta",
              "Sábado", "Domingo")

# Paleta principal (Okabe-Ito) — espelha o preâmbulo do artigo.
CORES = {
    "carga": "#56B4E9",       # corCarga
    "carga_bess": "#D55E00",  # corCargaBESS
    "import": "#0072B2",      # corImport
    "fv": "#E69F00",          # corFV
    "desc_bess": "#009E73",   # corDescBESS
    "texto": "#333333",
    "referencia": "#555555",
}

# Uma cor por dia da semana — espelha corSeg…corDom.
COR_POR_DIA = {
    "Segunda": "#E69F00",
    "Terça": "#56B4E9",
    "Quarta": "#009E73",
    "Quinta": "#CC79A7",
    "Sexta": "#0072B2",
    "Sábado": "#D55E00",
    "Domingo": "#7F7F7F",
}

# Um marcador por dia — permite distinguir as séries mesmo sem cor.
MARCADOR_POR_DIA = {
    "Segunda": "*",
    "Terça": "s",
    "Quarta": "^",
    "Quinta": "D",
    "Sexta": "p",
    "Sábado": "o",
    "Domingo": "x",
}

# A cada quantos pontos marcar (equivale ao mark repeat=2 do pgfplots).
CADA_N_HORAS = 2
TAM_MARCADOR = 4.0

_COR_PADRAO = CORES["referencia"]
_MARCADOR_PADRAO = "o"


def _sem_acento(texto: str) -> str:
    """Minúsculas, sem diacríticos — para casar 'Terça' com 'terca'."""
    decomposto = unicodedata.normalize("NFD", texto)
    return "".join(c for c in decomposto
                   if not unicodedata.combining(c)).strip().lower()


# Prefixos sem acento, pré-computados uma vez.
_PREFIXOS = tuple((_sem_acento(nome), nome) for nome in DIAS_NOMES)


def _normalizar_dia(valor) -> Optional[str]:
    """Resolve um dia (int ou texto livre) para o nome canônico.

    Aceita:
    - ``int``: índice 0-based em ``DIAS_NOMES`` (módulo 7 — 7 equivale a
      segunda, tolerante a ledgers que contem dias corridos).
    - ``str``: nome do dia, com ou sem acento, em qualquer caixa e com
      sufixo livre — ex.: ``"quinta (nublada)"`` → ``"Quinta"``.

    Devolve o nome canônico ou ``None`` se não casar.
    """
    if isinstance(valor, bool):
        return None
    if isinstance(valor, int):
        return DIAS_NOMES[valor % 7]
    if not isinstance(valor, str):
        return None
    limpo = _sem_acento(valor)
    if not limpo:
        return None
    for prefixo, canonico in _PREFIXOS:
        if limpo == prefixo or limpo.startswith(prefixo):
            return canonico
    return None


def cor_do_dia(valor) -> str:
    """Cor (hex) associada ao dia; cor de referência se não reconhecer."""
    nome = _normalizar_dia(valor)
    return COR_POR_DIA.get(nome, _COR_PADRAO) if nome else _COR_PADRAO


def marcador_do_dia(valor) -> str:
    """Marcador matplotlib associado ao dia; 'o' se não reconhecer."""
    nome = _normalizar_dia(valor)
    return MARCADOR_POR_DIA.get(nome, _MARCADOR_PADRAO) if nome else _MARCADOR_PADRAO


def serie_artigo(ax, dia, xs, ys, espessura: float = 1.0,
                 somente_marcas: bool = False,
                 label: Optional[str] = None):
    """Plota uma série no estilo do artigo para o dia informado.

    Cor e marcador vêm do dia; marcas a cada ``CADA_N_HORAS`` pontos.
    ``somente_marcas=True`` reproduz as curvas semanais do artigo (só
    pontos, sem linha) — a linha cheia fica para séries contínuas como
    SoC e potência do BESS.

    Devolve a lista de ``Line2D`` criada (vazia se não houver pontos).
    """
    xs = list(xs or [])
    ys = list(ys or [])
    if not xs or not ys:
        return []
    nome = _normalizar_dia(dia)
    rotulo = label if label is not None else (nome or "—")
    linha = ax.plot(
        xs[:len(ys)],
        ys,
        color=cor_do_dia(dia),
        marker=marcador_do_dia(dia),
        markersize=TAM_MARCADOR,
        markevery=CADA_N_HORAS,
        linestyle="none" if somente_marcas else "-",
        linewidth=espessura,
        label=rotulo,
    )
    return list(linha)
