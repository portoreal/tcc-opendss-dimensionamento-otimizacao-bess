__author__ = 'Pedro Henrique Sousa Pinheiro'
"""Model: estrutura de dados da rede elétrica (independente de interface)."""

import json
import re
from dataclasses import dataclass, field, asdict
from typing import Dict, Any, Optional, Iterable, List


def gerar_nome_unico(nome_base: str, nomes_existentes: Iterable[str]) -> str:
    """Garante um nome único dentro de 'nomes_existentes'.

    Se 'nome_base' ainda não existir, é usado sem alterações.
    Caso já exista, procura o MAIOR sufixo numérico já usado entre os
    nomes que seguem o padrão 'nome_base' + dígitos (opcional) e retorna
    'nome_base' + (maior_sufixo + 1).

    Exemplos:
        "linha" (livre)                          -> "linha"
        "linha" (já existe "linha")               -> "linha1"
        "linha" (já existem "linha","linha1"..4)  -> "linha5"
    """
    nome_base = nome_base.strip()
    nomes_existentes = set(nomes_existentes)

    if nome_base not in nomes_existentes:
        return nome_base

    padrao = re.compile(rf'^{re.escape(nome_base)}(\d*)$')
    maior_sufixo = 0

    for nome in nomes_existentes:
        m = padrao.match(nome)
        if m:
            sufixo = m.group(1)
            numero = int(sufixo) if sufixo else 0
            maior_sufixo = max(maior_sufixo, numero)

    return f"{nome_base}{maior_sufixo + 1}"


@dataclass
class Barra:
    nome: str
    kv_base: float = 13.8


@dataclass
class ElementoRamo:
    """Elemento que conecta DUAS barras (Line, Transformer, Switch)."""
    tipo: str
    nome: str
    bus1: str
    bus2: str
    parametros: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ElementoDerivacao:
    """Elemento conectado a UMA única barra (Load, Generator, Capacitor,
    PVSystem, Storage, Reactor, Vsource/Fonte) OU sem conexão física
    própria a nenhuma barra (InvControl, que referencia outro elemento
    via a propriedade DERList em seus parâmetros).

    O campo 'grupo' identifica a qual elemento composto (ex.: um "Sistema
    BESS" formado por Storage + InvControl + Capacitor/Reactor) este
    elemento pertence. Elementos avulsos (criados fora de um composto)
    têm grupo=None.
    """
    tipo: str
    nome: str
    bus1: Optional[str] = None
    parametros: Dict[str, Any] = field(default_factory=dict)
    grupo: Optional[str] = None


@dataclass
class CurvaXY:
    """Curva genérica X-Y do OpenDSS (New XYCurve...), usada atualmente
    pelas curvas Volt-Var/Volt-Watt do InvControl."""
    nome: str
    npts: int
    xarray: List[float] = field(default_factory=list)
    yarray: List[float] = field(default_factory=list)


class RedeEletrica:
    """Representa o grafo completo da rede: barras + ramos + derivações
    (+ curvas XY auxiliares, usadas por elementos como o InvControl)."""

    def __init__(self):
        self.barras: Dict[str, Barra] = {}
        self.ramos: Dict[str, ElementoRamo] = {}
        self.derivacoes: Dict[str, ElementoDerivacao] = {}
        self.curvas_xy: Dict[str, CurvaXY] = {}

    # ---------------------------- BARRAS ---------------------------- #
    def adicionar_barra(self, nome: str, kv_base: float = 13.8) -> str:
        """Cria a barra. Se o nome já existir, é auto-renomeada.
        Retorna o nome final efetivamente usado."""
        nome_final = gerar_nome_unico(nome, self.barras.keys())
        self.barras[nome_final] = Barra(nome_final, kv_base)
        return nome_final

    def remover_barra(self, nome: str):
        """Remove a barra e, em cascata, todos os elementos ligados a ela.

        Se algum dos elementos removidos pertencer a um grupo (ex.: um
        Sistema BESS composto), o GRUPO INTEIRO é removido também, mesmo
        que outros elementos do grupo (ex.: um InvControl, que não tem
        bus1 próprio) não estejam diretamente conectados a esta barra.
        Isso evita deixar elementos "órfãos" referenciando um elemento
        que já foi excluído (ex.: InvControl.DERList apontando para um
        Storage inexistente).
        """
        self.barras.pop(nome, None)

        for chave in [k for k, r in self.ramos.items() if nome in (r.bus1, r.bus2)]:
            self.ramos.pop(chave, None)

        grupos_a_remover = {
            d.grupo for d in self.derivacoes.values()
            if d.bus1 == nome and d.grupo
        }
        for grupo in grupos_a_remover:
            self.remover_grupo(grupo)

        for chave in [k for k, d in self.derivacoes.items() if d.bus1 == nome]:
            self.derivacoes.pop(chave, None)

    def renomear_barra(self, nome_antigo: str, nome_novo: str) -> str:
        """Renomeia uma barra, atualizando em cascata todas as referências
        em ramos e derivações. Se o novo nome colidir com outra barra
        existente, é auto-renomeado. Retorna o nome final."""

        if nome_antigo not in self.barras:
            raise ValueError(f"Barra '{nome_antigo}' não encontrada.")

        nome_final = nome_novo.strip()
        if nome_final != nome_antigo:
            outros_nomes = [n for n in self.barras if n != nome_antigo]
            nome_final = gerar_nome_unico(nome_final, outros_nomes)

        barra = self.barras.pop(nome_antigo)
        barra.nome = nome_final
        self.barras[nome_final] = barra

        for ramo in self.ramos.values():
            if ramo.bus1 == nome_antigo:
                ramo.bus1 = nome_final
            if ramo.bus2 == nome_antigo:
                ramo.bus2 = nome_final

        for der in self.derivacoes.values():
            if der.bus1 == nome_antigo:
                der.bus1 = nome_final

        return nome_final

    # ---------------------------- RAMOS ---------------------------- #
    def adicionar_ramo(self, tipo: str, nome: str, bus1: str, bus2: str,
                        parametros: Optional[Dict[str, Any]] = None) -> str:
        """Cria o ramo. Se o nome já existir, é auto-renomeado.
        Retorna o nome final efetivamente usado."""

        if bus1 not in self.barras or bus2 not in self.barras:
            raise ValueError("Ambas as barras precisam existir antes de criar o ramo.")
        if bus1 == bus2:
            raise ValueError("A barra de origem e destino devem ser diferentes.")

        nome_final = gerar_nome_unico(nome, self.ramos.keys())
        self.ramos[nome_final] = ElementoRamo(tipo, nome_final, bus1, bus2, parametros or {})
        return nome_final

    def remover_ramo(self, nome: str):
        self.ramos.pop(nome, None)

    # -------------------------- DERIVAÇÕES -------------------------- #
    def adicionar_derivacao(self, tipo: str, nome: str, bus1: Optional[str] = None,
                             parametros: Optional[Dict[str, Any]] = None,
                             grupo: Optional[str] = None) -> str:
        """Cria o elemento conectado. Se o nome já existir, é auto-renomeado.
        Retorna o nome final efetivamente usado.

        bus1=None é permitido apenas para elementos que não se conectam
        fisicamente a uma barra (ex.: InvControl, que referencia outro
        elemento via a propriedade DERList em seus parâmetros).
        """

        if bus1 is not None and bus1 not in self.barras:
            raise ValueError("A barra precisa existir antes de conectar o elemento.")

        nome_final = gerar_nome_unico(nome, self.derivacoes.keys())
        self.derivacoes[nome_final] = ElementoDerivacao(
            tipo, nome_final, bus1, parametros or {}, grupo)
        return nome_final

    def remover_derivacao(self, nome: str):
        self.derivacoes.pop(nome, None)

    def remover_grupo(self, nome_grupo: str):
        """Remove TODOS os elementos (derivações) que pertencem ao mesmo
        grupo lógico (ex.: um Sistema BESS composto por Storage +
        InvControl + Capacitor/Reator). Usado para exclusão em cascata a
        partir de qualquer ponto de entrada (barra removida, ou exclusão
        explícita do conjunto pelo usuário)."""
        for chave in [k for k, d in self.derivacoes.items() if d.grupo == nome_grupo]:
            self.derivacoes.pop(chave, None)

    def obter_grupo(self, nome_grupo: str) -> Dict[str, ElementoDerivacao]:
        """Retorna todos os elementos (derivações) que pertencem a um
        determinado grupo (ex.: os elementos internos de um Sistema BESS)."""
        return {k: d for k, d in self.derivacoes.items() if d.grupo == nome_grupo}

    def obter_fonte(self) -> Optional[ElementoDerivacao]:
        fontes = [d for d in self.derivacoes.values() if d.tipo == "Vsource"]
        return fontes[0] if fontes else None

    # --------------------------- CURVAS XY --------------------------- #
    def adicionar_curva_xy(self, nome: str, xarray: List[float], yarray: List[float]) -> str:
        """Adiciona uma curva XYCurve (ex.: usada pelo InvControl para
        Volt-Var/Volt-Watt).

        Se já existir uma curva com o MESMO nome e o MESMO conteúdo
        (xarray/yarray), reaproveita-a (evita duplicar a mesma curva
        padrão toda vez que um novo Sistema BESS é criado). Se existir
        uma curva com o mesmo nome mas conteúdo DIFERENTE, a nova é
        auto-renomeada. Retorna o nome final efetivamente usado.
        """
        existente = self.curvas_xy.get(nome)

        if existente is None:
            self.curvas_xy[nome] = CurvaXY(nome, len(xarray), list(xarray), list(yarray))
            return nome

        if list(existente.xarray) == list(xarray) and list(existente.yarray) == list(yarray):
            return nome

        nome_final = gerar_nome_unico(nome, self.curvas_xy.keys())
        self.curvas_xy[nome_final] = CurvaXY(nome_final, len(xarray), list(xarray), list(yarray))
        return nome_final

    # --------------------------- PERSISTÊNCIA --------------------------- #
    def to_dict(self) -> dict:
        return {
            "barras": {k: asdict(v) for k, v in self.barras.items()},
            "ramos": {k: asdict(v) for k, v in self.ramos.items()},
            "derivacoes": {k: asdict(v) for k, v in self.derivacoes.items()},
            "curvas_xy": {k: asdict(v) for k, v in self.curvas_xy.items()},
        }

    def salvar_json(self, caminho: str):
        with open(caminho, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)

    @classmethod
    def carregar_json(cls, caminho: str) -> "RedeEletrica":
        with open(caminho, "r", encoding="utf-8") as f:
            dados = json.load(f)

        rede = cls()
        for nome, b in dados.get("barras", {}).items():
            b_filtrado = {k: v for k, v in b.items() if k in ("nome", "kv_base")}
            rede.barras[nome] = Barra(**b_filtrado)
        for nome, r in dados.get("ramos", {}).items():
            rede.ramos[nome] = ElementoRamo(**r)
        for nome, d in dados.get("derivacoes", {}).items():
            # Compatível com arquivos salvos ANTES da introdução dos
            # campos 'grupo' e bus1 opcional: se ausentes no JSON, os
            # valores padrão do dataclass (None) são usados automaticamente.
            rede.derivacoes[nome] = ElementoDerivacao(**d)
        for nome, c in dados.get("curvas_xy", {}).items():
            rede.curvas_xy[nome] = CurvaXY(**c)

        return rede