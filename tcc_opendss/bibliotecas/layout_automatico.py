__author__ = 'Pedro Henrique Sousa Pinheiro'
"""Posições (x, y) das barras no diagrama, calculadas em camadas.

O desenho segue uma versão simplificada do layout Sugiyama: cada barra cai
num nível, medido em número de ramos a partir de uma raiz, e os níveis são
empilhados. A barra da Fonte (Vsource), quando existe, é a raiz do
primeiro componente e ocupa o nível 0.

Todo grupo de barras conectadas entre si recebe sua própria hierarquia por
BFS, mesmo sem Fonte. Sem isso, uma rede ainda em montagem — sem Vsource
cadastrada — colapsaria numa única fileira horizontal e ficaria ilegível.
"""

from collections import deque
from typing import Dict, Tuple

from .modelo_rede import RedeEletrica


def _construir_adjacencia(rede: RedeEletrica) -> Dict[str, set]:
    # Lista de vizinhos de cada barra, montada a partir dos ramos. A lista
    # é não-direcionada de propósito: para posicionar não importa o sentido
    # do fluxo, só quem está eletricamente ao lado de quem.
    adjacencia = {nome: set() for nome in rede.barras}
    for ramo in rede.ramos.values():
        # Ramo com extremidade em barra inexistente é ignorado. O modelo
        # permite esse estado transitório enquanto o usuário edita, e o
        # layout não pode quebrar por causa disso.
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
        """Percorre largura-primeiro a partir de 'origem' e devolve o maior
        nível alcançado.

        Largura-primeiro (BFS) garante que toda barra receba o menor número
        de ramos possível até a raiz — é isso que dá ao diagrama a forma de
        árvore, com a fonte em cima e as cargas abaixo. O maior nível
        devolvido serve para saber onde o próximo componente pode começar
        sem sobrepor este.
        """
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

    # 1) O componente da Fonte (Vsource) vem primeiro, se existir: é o
    #    único que tem raiz natural, então o layout inteiro se organiza a
    #    partir dele.
    fonte = rede.obter_fonte()
    if fonte and fonte.bus1 in todas_barras:
        maior_nivel = bfs_a_partir_de(fonte.bus1, 0)
        # O "+2" (e não "+1") abre um vão entre componentes. Sem o vão, a
        # última barra de um componente e a primeira do seguinte ficariam
        # na mesma altura e pareceriam conectadas.
        proximo_nivel_livre = maior_nivel + 2

    # 2) Barra ainda não visitada inicia um novo componente (rede
    #    desconexa, que é comum durante a edição). A ordem alfabética
    #    mantém o resultado estável entre execuções — sem ela, a posição
    #    mudaria a cada abertura do projeto.
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
    """Devolve {nome_da_barra: (x, y)}, em pixels do canvas.

    As distâncias padrão (160 px entre níveis, 140 px entre barras do mesmo
    nível) foram escolhidas para caber o rótulo da barra e o do ramo sem
    sobreposição na escala inicial do editor. Aumente-as se o projeto tiver
    nomes longos.
    """

    niveis = _calcular_niveis(rede)

    agrupado_por_nivel: Dict[int, list] = {}
    for nome, nivel in niveis.items():
        agrupado_por_nivel.setdefault(nivel, []).append(nome)

    for nomes in agrupado_por_nivel.values():
        # Ordem alfabética dentro do nível: barras do mesmo nível não têm
        # relação de hierarquia entre si, então qualquer critério serve —
        # desde que seja estável.
        nomes.sort()

    posicoes: Dict[str, Tuple[float, float]] = {}

    for nivel in sorted(agrupado_por_nivel.keys()):
        nomes = agrupado_por_nivel[nivel]
        quantidade = len(nomes)
        largura_total = (quantidade - 1) * espacamento_lateral

        for i, nome in enumerate(nomes):
            # Distribui o nível em torno do centro, e não a partir da
            # margem esquerda: um nível com poucas barras fica centrado
            # sob o anterior, em vez de pendurado à esquerda.
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