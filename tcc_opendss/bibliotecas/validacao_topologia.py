__author__ = 'Pedro Henrique Sousa Pinheiro'
"""Desenho da topologia dos sistemas de referência IEEE utilizados na
Validação do Modelo Computacional, a partir das coordenadas oficiais
(BusCoords) e das listas de linhas, chaves, transformadores e
reguladores de tensão do circuito compilado.

Este módulo é puramente de VISUALIZAÇÃO/DOCUMENTAÇÃO: não realiza
nenhum cálculo elétrico, apenas organiza graficamente o resultado já
obtido pela simulação (ver validacao_ieee.py), reaproveitando a mesma
instância do circuito já resolvida, para evitar uma segunda compilação.

CONVENÇÃO VISUAL ADOTADA (segregação por tipo de elemento):
    - Linha de distribuição comum : linha contínua cinza.
    - Chave (switch)              : linha tracejada cinza.
    - Transformador de distribuição : linha contínua verde.
    - Regulador de tensão (banco de transformadores sob RegControl):
                                     linha tracejada verde.

Essa distinção depende dos métodos obter_linhas() e
obter_transformadores() de dss_engine.py retornarem, respectivamente,
a flag 'e_chave' e 'e_regulador' para cada elemento.

CORREÇÃO DE BUG (registrada por transparência metodológica): versões
anteriores deste módulo filtravam, antes do desenho, qualquer barra
cuja coordenada fosse exatamente (0, 0), sob a suposição de que esse
seria sempre o valor padrão atribuído pelo OpenDSS a barras SEM
Buscoords definido. Essa suposição se mostrou incorreta: ao menos duas
barras com coordenada OFICIAL e legítima exatamente em (0, 0) foram
identificadas nos arquivos de referência do IEEE - a barra '800' no
sistema de 34 nós e a barra '799r' no sistema de 37 nós. O filtro foi
removido; todas as barras retornadas por obter_coordenadas_barras()
são desenhadas, independentemente do valor de sua coordenada.
"""

import matplotlib.pyplot as plt
import matplotlib.lines as mlines
import matplotlib.patches as mpatches


# Paleta de cores/estilos por tipo de elemento, centralizada para
# facilitar eventual ajuste futuro sem precisar alterar a lógica de
# desenho em si.
ESTILO_LINHA = {"color": "#555555", "linewidth": 1.2, "linestyle": "-"}
ESTILO_CHAVE = {"color": "#555555", "linewidth": 1.2, "linestyle": "--"}
ESTILO_TRANSFORMADOR = {"color": "#2ca02c", "linewidth": 1.6, "linestyle": "-"}
ESTILO_REGULADOR = {"color": "#2ca02c", "linewidth": 1.6, "linestyle": "--"}


def desenhar_topologia(objeto_dss, titulo: str, barras_destacadas: dict = None):
    """Desenha a topologia do circuito ativo em objeto_dss, usando as
    coordenadas carregadas via Buscoords e as listas de linhas, chaves,
    transformadores e reguladores do circuito.

    Parameters
    ----------
    objeto_dss : dss_engine.DSS
        Instância já compilada e resolvida (reaproveitada da própria
        validação, sem precisar recompilar).
    titulo : str
        Título do gráfico (ex.: nome do sistema).
    barras_destacadas : dict, opcional
        {nome_barra: cor}, usado para destacar visualmente barras de
        interesse (ex.: exceções documentadas, barras com maior erro).

    Retorna a Figure do matplotlib, para ser embutida em uma interface
    Tkinter (via FigureCanvasTkAgg) ou salva em arquivo.
    """

    barras_destacadas = barras_destacadas or {}

    coordenadas = objeto_dss.obter_coordenadas_barras()
    linhas_brutas = objeto_dss.obter_linhas()
    transformadores_brutos = objeto_dss.obter_transformadores()

    # Segrega linhas comuns de chaves (ambas vêm de obter_linhas(),
    # diferenciadas pela flag e_chave).
    linhas = [(b1, b2) for (b1, b2, e_chave) in linhas_brutas if not e_chave]
    chaves = [(b1, b2) for (b1, b2, e_chave) in linhas_brutas if e_chave]

    # Segrega transformadores comuns de reguladores de tensão (ambos
    # vêm de obter_transformadores(), diferenciados pela flag
    # e_regulador).
    transformadores = [
        (b1, b2) for (b1, b2, e_regulador) in transformadores_brutos if not e_regulador
    ]
    reguladores = [
        (b1, b2) for (b1, b2, e_regulador) in transformadores_brutos if e_regulador
    ]

    figura, eixo = plt.subplots(figsize=(8, 7))
    # Figura menor em número de barras exige menos pixels; nas redes
    # grandes (123 barras) o tamanho maior é o que torna os rótulos
    # legíveis quando a imagem é exibida ajustada à aba.
    figura.set_size_inches(
        min(26.0, max(8.0, 0.20 * len(coordenadas) + 6.0)),
        min(20.0, max(7.0, 0.16 * len(coordenadas) + 5.0)),
    )

    def _desenhar_conjunto(pares, estilo):
        for bus1, bus2 in pares:
            p1 = coordenadas.get(bus1)
            p2 = coordenadas.get(bus2)
            if p1 and p2:
                eixo.plot([p1[0], p2[0]], [p1[1], p2[1]], zorder=1, **estilo)

    # ---- Arestas, por tipo de elemento (ordem não afeta o resultado) ---- #
    _desenhar_conjunto(linhas, ESTILO_LINHA)
    _desenhar_conjunto(chaves, ESTILO_CHAVE)
    _desenhar_conjunto(transformadores, ESTILO_TRANSFORMADOR)
    _desenhar_conjunto(reguladores, ESTILO_REGULADOR)

    # ---- Barras (nós) ---- #
    for nome, (x, y) in coordenadas.items():
        cor = barras_destacadas.get(nome.upper(), "#1f77b4")
        tamanho = 60 if nome.upper() in barras_destacadas else 25
        eixo.scatter(x, y, s=tamanho, color=cor, zorder=2,
                     edgecolors="black", linewidths=0.5)

    eixo.set_title(titulo, fontsize=12, fontweight="bold")
    eixo.set_xlabel("Coordenada X (unidade arbitrária, conforme BusCoords)")
    eixo.set_ylabel("Coordenada Y (unidade arbitrária, conforme BusCoords)")
    eixo.set_aspect("equal", adjustable="datalim")
    eixo.grid(True, linestyle=":", alpha=0.4)

    # ---- Legenda (somente para os tipos efetivamente presentes) ---- #
    legendas = []
    if linhas:
        legendas.append(mlines.Line2D([], [], label="Linha", **ESTILO_LINHA))
    if chaves:
        legendas.append(mlines.Line2D([], [], label="Chave (switch)", **ESTILO_CHAVE))
    if transformadores:
        legendas.append(mlines.Line2D([], [], label="Transformador", **ESTILO_TRANSFORMADOR))
    if reguladores:
        legendas.append(mlines.Line2D([], [], label="Regulador de tensão", **ESTILO_REGULADOR))
    for nome, cor in barras_destacadas.items():
        legendas.append(mpatches.Patch(color=cor, label=f"Barra {nome}"))

    if legendas:
        eixo.legend(handles=legendas, loc="best", fontsize=8)

    figura.tight_layout()
    return figura


def salvar_topologia_png(figura, caminho_arquivo: str, dpi: int = 150):
    figura.savefig(caminho_arquivo, dpi=dpi, bbox_inches="tight")