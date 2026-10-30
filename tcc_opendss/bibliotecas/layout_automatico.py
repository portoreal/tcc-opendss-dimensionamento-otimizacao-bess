__author__ = 'Pedro Henrique Sousa Pinheiro'
"""Calcula automaticamente as posições (x, y) das barras para exibição,
usando um layout em camadas (layered layout / estilo Sugiyama simplificado).

A barra com a Fonte (Vsource), se existir, é a raiz do primeiro componente
(nível 0). Qualquer outro grupo de barras conectadas entre si (mesmo sem
Fonte) também recebe sua própria hierarquia via BFS, evitando que toda a
rede "colapse" visualmente em uma única fileira quando ainda não há Fonte
cadastrada.
"""

from collections import deque
from typing import Dict, Tuple

from .modelo_rede import RedeEletrica


def _construir_adjacencia(rede: RedeEletrica) -> Dict[str, set]:
    adjacencia = {nome: set() for nome in rede.barras}
    for ramo in rede.ramos.values():
        if ramo.bus1 in adjacencia and ramo.bus2 in adjacencia:
            adjacencia[ramo.bus1].add(ramo.bus2)
            adjacencia[ramo.bus2].add(ramo.bus1)
    return adjacencia


def _calcular_niveis(rede: RedeEletrica) -> Dict[str, int]:
    adjacencia = _construir_adjacencia(rede)
    todas_barras = set(rede.barras.keys())

    niveis: Dict[str, int] = {}
    visitados = set()

    def bfs_a_partir_de(origem: str, nivel_inicial: int) -> int:
        """Executa o BFS a partir de 'origem', preservando a hierarquia
        interna do componente. Retorna o maior nível encontrado."""
        niveis[origem] = nivel_inicial
        visitados.add(origem)
        fila = deque([origem])
        maior_nivel = nivel_inicial

        while fila:
            atual = fila.popleft()
            for vizinho in sorted(adjacencia.get(atual, ())):
                if vizinho not in visitados:
                    visitados.add(vizinho)
                    niveis[vizinho] = niveis[atual] + 1
                    maior_nivel = max(maior_nivel, niveis[vizinho])
                    fila.append(vizinho)

        return maior_nivel

    proximo_nivel_livre = 0

    # 1) Prioriza o componente que contém a Fonte (Vsource), se existir.
    fonte = rede.obter_fonte()
    if fonte and fonte.bus1 in todas_barras:
        maior_nivel = bfs_a_partir_de(fonte.bus1, 0)
        proximo_nivel_livre = maior_nivel + 2  # espaço de separação visual

    # 2) Qualquer barra ainda não visitada vira raiz de um novo componente,
    #    preservando a hierarquia interna dele (em vez de jogar tudo no
    #    mesmo nível, que era o bug original).
    for nome in sorted(todas_barras):
        if nome not in visitados:
            maior_nivel = bfs_a_partir_de(nome, proximo_nivel_livre)
            proximo_nivel_livre = maior_nivel + 2

    return niveis


def calcular_posicoes(
    rede: RedeEletrica,
    orientacao: str = "vertical",
    espacamento_nivel: float = 160,
    espacamento_lateral: float = 140,
    margem: float = 80,
    centro: float = 450,
) -> Dict[str, Tuple[float, float]]:
    """Retorna {nome_da_barra: (x, y)} calculado automaticamente."""

    niveis = _calcular_niveis(rede)

    agrupado_por_nivel: Dict[int, list] = {}
    for nome, nivel in niveis.items():
        agrupado_por_nivel.setdefault(nivel, []).append(nome)

    for nomes in agrupado_por_nivel.values():
        nomes.sort()  # ordem estável e previsível

    posicoes: Dict[str, Tuple[float, float]] = {}

    for nivel in sorted(agrupado_por_nivel.keys()):
        nomes = agrupado_por_nivel[nivel]
        quantidade = len(nomes)
        largura_total = (quantidade - 1) * espacamento_lateral

        for i, nome in enumerate(nomes):
            deslocamento_lateral = i * espacamento_lateral - largura_total / 2
            coordenada_principal = margem + nivel * espacamento_nivel

            if orientacao == "vertical":
                x = centro + deslocamento_lateral
                y = coordenada_principal
            else:  # horizontal
                x = coordenada_principal
                y = centro + deslocamento_lateral

            posicoes[nome] = (x, y)

    return posicoes