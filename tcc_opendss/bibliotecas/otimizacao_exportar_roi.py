# -*- coding: utf-8 -*-
"""
Exportador HTML de Justificativa de Investimento (ROI/DRE) — Otimização de BESS.

Gera um relatório standalone (HTML5, UTF-8, CSS inline, sem JavaScript e sem
CDN) a partir do dicionário devolvido por
``otimizacao_bess.executar_estudo_completo``. O documento é voltado à decisão de
investimento: cartões executivos, DRE anual sem O&M, projeção multi-anual do
fluxo de caixa, quatro gráficos embutidos como PNG base64, avaliação da
qualidade de energia, alertas operacionais, panorama de incentivos regulatórios
e premissas/metodologia no rodapé.

TRANSPARÊNCIA TÉCNICA
---------------------
* Entrada: o schema de ``resultado`` é o contrato real de
  ``executar_estudo_completo``. Este módulo não recalcula o estudo; apenas
  apresenta, converte e formata os números já apurados.
* O motor numérico devolve ``numpy.float64``/``numpy.int64`` em pontos diversos
  (somam-se a ``set`` de ``barras_em_sag_geral``). Todo valor numérico é
  convertido explicitamente com ``float()``/``int()``/``bool()`` antes de ser
  formatado ou somado, evitando vazamento de tipos numpy para a formatação.
* A profundidade de afundamento por barra é obtida de
  ``otimizacao_bess._profundidades_por_barra`` (import tardio, para não acoplar
  o import deste módulo ao carregamento do motor e das dependências OpenDSS).
* O eixo de tempo do perfil horário é o do estudo (24 pontos, hora inteira).
* Formatação pt-BR é feita por helpers próprios (milhar '.' e decimal ','), sem
  ``locale`` do sistema — o locale global do processo não é alterado nem
  consultado.
* Matplotlib é importado com backend ``Agg`` forçado antes de ``pyplot``, porque
  o módulo pode ser executado em contexto headless (servidor, console, teste).
* O relatório não monetiza energia exportada, não modela O&M nem degradação e
  não aplica tributos: essas limitações estão declaradas explicitamente na nota
  da DRE e no rodapé de premissas.

TRANSPARÊNCIA TÉCNICA — PREMISSAS DO RELATÓRIO
----------------------------------------------
* Receita anual de energia = ``resultado_economia["economia_anual"]``.
* Receita anual de demanda = ``economia_demanda_mensal_estimada * 12``.
* Payback simples = CAPEX / receita total anual; indefinido (``None``) quando a
  receita é nula ou negativa.
* ROI anual = receita total anual / CAPEX * 100.
* Horizonte de projeção = ``min(max(ceil(payback) + 2, 10), 25)`` anos; quando o
  payback é inválido, adota-se 10 anos.
* Redução média de severidade = ``(1 - Σapós/Σantes) * 100`` quando
  ``Σantes > 0``; caso contrário ``—``.

TRANSPARÊNCIA TÉCNICA — ALERTAS
-------------------------------
Os alertas reproduzem os sinalizadores do estudo econômico
(``alerta_superdimensionamento``, ``alerta_caso_base_exportacao``) e o volume
exportado no período de análise. Nenhum deles é recalculado aqui.

TRANSPARÊNCIA TÉCNICA — INCENTIVOS
----------------------------------
A lista ``INCENTIVOS_PADRAO`` é conteúdo editorial estático sobre o marco
regulatório brasileiro de armazenamento. Cada item carrega fonte e nota de
verificação; o relatório declara que a vigência e as condições devem ser
confirmadas nas fontes oficiais antes de uso executivo.

Autor: Pedro Henrique Sousa Pinheiro
"""

from __future__ import annotations

import base64
import datetime as _dt
import io
import math
import os

__author__ = "Pedro Henrique Sousa Pinheiro"

__all__ = [
    "INCENTIVOS_PADRAO",
    "gerar_relatorio_roi",
]

# ---------------------------------------------------------------------------
# Constantes visuais
# ---------------------------------------------------------------------------

_ACCENT = "#004587"
_BORDA = "#D5DBE3"
_ZEBRA = "#F7F9FC"
_TEXTO = "#1A2733"
_TEXTO_SUAVE = "#5A6672"
_AMBAR_BG = "#FFF7E0"
_AMBAR_BORDA = "#E0A800"
_VERDE_BG = "#EAF7EE"
_VERDE_BORDA = "#2E7D32"
_CINZA_PONTA = "#D9DEE5"

_COR_BASE = "#9AA5B1"
_COR_BESS = "#004587"
_COR_POSITIVO = "#1B7F3B"
_COR_NEGATIVO = "#B3261E"

_NOTA_DRE = (
    "Custos de operação e manutenção e degradação da bateria não são modelados "
    "pelo estudo; a energia exportada não é monetizada; os valores da tarifa "
    "seguem a fonte informada (eventualmente sem tributos)."
)


# ---------------------------------------------------------------------------
# Formatação pt-BR (sem locale do sistema)
# ---------------------------------------------------------------------------


def _fmt_num(valor, casas: int = 2) -> str:
    """
    Formata número no padrão pt-BR (milhar '.', decimal ',').

    TRANSPARÊNCIA TÉCNICA: não usa ``locale``; a conversão é aritmética, de modo
    que o resultado independe da configuração regional do processo.

    Args:
        valor: número (int, float, numpy) ou ``None``.
        casas: casas decimais desejadas.

    Returns:
        String formatada ou ``"—"`` quando o valor é ``None``/não numérico.
    """
    if valor is None:
        return "—"
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        return "—"
    if not math.isfinite(numero):
        return "—"
    casas = max(int(casas), 0)
    texto = f"{abs(numero):.{casas}f}"
    inteiro, _, decimal = texto.partition(".")
    grupos = []
    while len(inteiro) > 3:
        grupos.insert(0, inteiro[-3:])
        inteiro = inteiro[:-3]
    grupos.insert(0, inteiro)
    saida = ".".join(grupos)
    if decimal:
        saida = f"{saida},{decimal}"
    if numero < 0:
        saida = "-" + saida
    return saida


def _fmt_brl(valor, casas: int = 2) -> str:
    """
    Formata valor monetário em reais no padrão pt-BR.

    TRANSPARÊNCIA TÉCNICA: apenas prefixa ``R$`` ao resultado de ``_fmt_num``.
    """
    if valor is None:
        return "—"
    formatado = _fmt_num(valor, casas)
    if formatado == "—":
        return "—"
    return f"R$ {formatado}"


def _fmt_pct(valor, casas: int = 1) -> str:
    """
    Formata percentual no padrão pt-BR.

    TRANSPARÊNCIA TÉCNICA: recebe o valor já em pontos percentuais (ex.: 12.5 →
    "12,5%"); não multiplica por 100.
    """
    if valor is None:
        return "—"
    formatado = _fmt_num(valor, casas)
    if formatado == "—":
        return "—"
    return f"{formatado}%"


def _fmt_anos(valor) -> str:
    """
    Formata prazo em anos.

    TRANSPARÊNCIA TÉCNICA: singular/plural conforme o valor arredondado.
    """
    if valor is None:
        return "—"
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        return "—"
    if not math.isfinite(numero):
        return "—"
    texto = _fmt_num(numero, 1)
    if texto == "—":
        return "—"
    return f"{texto} ano" if abs(numero - 1.0) < 1e-9 else f"{texto} anos"


def _escapar(texto) -> str:
    """
    Escapa texto para inserção segura em HTML.

    TRANSPARÊNCIA TÉCNICA: os dados vêm do estudo (nomes de projeto, barras,
    modelo). Ainda assim todo texto dinâmico passa por escape — um nome de
    projeto com ``<`` ou ``&`` não pode corromper a estrutura do documento.
    """
    if texto is None:
        return ""
    return (
        str(texto)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


# ---------------------------------------------------------------------------
# Conversão defensiva dos dados de entrada
# ---------------------------------------------------------------------------


def _to_float(valor, padrao: float = 0.0) -> float:
    """
    Converte para ``float`` absorvendo numpy e valores ausentes.

    TRANSPARÊNCIA TÉCNICA: o motor devolve ``numpy.float64``; ``float()`` é
    explícito para impedir que a formatação receba tipos numéricos do numpy.
    """
    if valor is None:
        return padrao
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        return padrao
    return numero if math.isfinite(numero) else padrao


def _to_opt_float(valor):
    """Converte para ``float`` ou ``None`` quando ausente/não finito."""
    if valor is None:
        return None
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        return None
    return numero if math.isfinite(numero) else None


def _to_int(valor, padrao: int = 0) -> int:
    """Converte para ``int`` absorvendo numpy e valores ausentes."""
    if valor is None:
        return padrao
    try:
        return int(valor)
    except (TypeError, ValueError):
        return padrao


def _to_bool(valor) -> bool:
    """Converte para ``bool`` absorvendo numpy e valores ausentes."""
    if valor is None:
        return False
    try:
        return bool(valor)
    except (TypeError, ValueError):
        return False


def _ordena_barras(nomes) -> list:
    """
    Ordena nomes de barra de forma natural (``02`` antes de ``10``).

    TRANSPARÊNCIA TÉCNICA: a ordenação é textual com chave numérica quando o
    nome é inteiramente numérico; caso contrário, alfabética. Garante saída
    determinística independente da ordem de iteração de ``set``.
    """
    lista = [str(nome) for nome in (nomes or [])]

    def _chave(nome: str):
        if nome.isdigit():
            return (0, int(nome), nome)
        return (1, 0, nome)

    return sorted(set(lista), key=_chave)


# ---------------------------------------------------------------------------
# Coleta/derivação de métricas
# ---------------------------------------------------------------------------


def _capital_bess(selecionados) -> float:
    """
    Soma o CAPEX (``custo_brl``) dos modelos BESS selecionados.

    TRANSPARÊNCIA TÉCNICA: cada item pode carregar um único modelo ou uma lista
    em ``modelos_bess``; ambos os formatos são aceitos e somados.
    """
    total = 0.0
    for item in selecionados or []:
        if not isinstance(item, dict):
            continue
        modelo = item.get("modelo_bess")
        if isinstance(modelo, dict):
            total += _to_float(modelo.get("custo_brl"), 0.0)
        modelos = item.get("modelos_bess")
        if isinstance(modelos, (list, tuple)):
            for extra in modelos:
                if isinstance(extra, dict):
                    total += _to_float(extra.get("custo_brl"), 0.0)
    return total


def _soma_profundidades(resultado_cenario, limite_superior: float) -> float:
    """
    Soma as profundidades por barra de um cenário.

    TRANSPARÊNCIA TÉCNICA: usa ``_profundidades_por_barra`` do motor; falhas de
    importação ou de cálculo degradam para ``0.0`` em vez de interromper a
    geração do relatório — o relatório é documento de saída, não motor de
    cálculo, e um cenário ilegível não deve inviabilizar a justificativa.
    """
    if not isinstance(resultado_cenario, dict):
        return 0.0
    try:
        from .otimizacao_bess import _profundidades_por_barra
    except Exception:  # pragma: no cover - fallback defensivo
        return 0.0
    try:
        profundidades = _profundidades_por_barra(resultado_cenario, limite_superior)
    except Exception:  # pragma: no cover - fallback defensivo
        return 0.0
    if not isinstance(profundidades, dict):
        return 0.0
    return sum(_to_float(valor, 0.0) for valor in profundidades.values())


def _profundidades_seguras(resultado_cenario, limite_superior: float) -> dict:
    """
    Devolve ``{barra: profundidade}`` em ``float``, tolerando falhas.

    TRANSPARÊNCIA TÉCNICA: mesma política de degradação de
    ``_soma_profundidades``; o dicionário resultante é sempre ``{str: float}``.
    """
    if not isinstance(resultado_cenario, dict):
        return {}
    try:
        from .otimizacao_bess import _profundidades_por_barra
    except Exception:  # pragma: no cover - fallback defensivo
        return {}
    try:
        brutas = _profundidades_por_barra(resultado_cenario, limite_superior)
    except Exception:  # pragma: no cover - fallback defensivo
        return {}
    if not isinstance(brutas, dict):
        return {}
    return {str(barra): _to_float(valor, 0.0) for barra, valor in brutas.items()}


def _horizonte_projecao(payback) -> int:
    """
    Define o horizonte (anos) da projeção multi-anual.

    TRANSPARÊNCIA TÉCNICA: ``min(max(ceil(payback) + 2, 10), 25)`` — nunca abaixo
    de 10 anos (horizonte mínimo para leitura de tendência) nem acima de 25
    (limite de plausibilidade de premissa tarifária constante). Payback inválido
    (``None``, não finito ou negativo) implica 10 anos.
    """
    payback_num = _to_opt_float(payback)
    if payback_num is None or payback_num < 0:
        return 10
    try:
        anos = int(math.ceil(payback_num)) + 2
    except (OverflowError, ValueError):
        return 10
    return int(min(max(anos, 10), 25))


def _perfil_horario(perfil, chave_chave: str = "kw_comprada") -> list:
    """
    Extrai a série de um perfil horário de 24 pontos.

    TRANSPARÊNCIA TÉCNICA: aceita itens como dicionário (chaves do contrato) ou
    tuplas; o eixo X é o índice quando ``hora`` está ausente. Série incompleta
    não é completada com zeros — o gráfico simplesmente não é gerado.
    """
    if not isinstance(perfil, (list, tuple)) or not perfil:
        return []
    serie = []
    for indice, ponto in enumerate(perfil):
        if isinstance(ponto, dict):
            serie.append(_to_float(ponto.get(chave_chave), 0.0))
        elif isinstance(ponto, (list, tuple)) and len(ponto) >= 3:
            try:
                serie.append(_to_float(ponto[2], 0.0))
            except IndexError:  # pragma: no cover - defensivo
                serie.append(0.0)
        else:
            serie.append(0.0)
    return serie


def _horas_ponta(perfil) -> set:
    """
    Identifica as horas marcadas como ponta no perfil.

    TRANSPARÊNCIA TÉCNICA: usa a bandeira ``ponta`` do próprio estudo; se
    ausente, o conjunto volta vazio e a faixa de ponta não é sombreada.
    """
    horas = set()
    if not isinstance(perfil, (list, tuple)):
        return horas
    for indice, ponto in enumerate(perfil):
        if not isinstance(ponto, dict):
            continue
        if _to_bool(ponto.get("ponta")):
            horas.add(_to_int(ponto.get("hora"), indice))
    return sorted(horas) and horas or set()


# ---------------------------------------------------------------------------
# Matplotlib (backend Agg obrigatório, figuras em memória)
# ---------------------------------------------------------------------------


def _pyplot():
    """
    Importa ``pyplot`` garantindo o backend ``Agg``.

    TRANSPARÊNCIA TÉCNICA: ``matplotlib.use("Agg")`` é executado antes do import
    de ``pyplot``. Em ambiente interativo com backend já fixado, a chamada pode
    falhar com exceção; ela é absorvida para não impedir a geração do relatório
    (a figura continua sendo salva em memória, sem janela).
    """
    import matplotlib

    try:
        matplotlib.use("Agg")
    except Exception:  # pragma: no cover - backend já fixado
        pass
    import matplotlib.pyplot as plt

    return plt


def _estilo_eixos(ax) -> None:
    """
    Aplica o estilo padrão dos gráficos do relatório.

    TRANSPARÊNCIA TÉCNICA: grade clara, molduras suavizadas e tipografia
    reduzida — apenas estética, sem impacto numérico.
    """
    ax.grid(True, color="#E4E9EF", linewidth=0.8, zorder=0)
    ax.set_axisbelow(True)
    for lado in ("top", "right"):
        if lado in ax.spines:
            ax.spines[lado].set_visible(False)
    for lado in ("left", "bottom"):
        if lado in ax.spines:
            ax.spines[lado].set_color("#C8D0D8")
    ax.tick_params(colors=_TEXTO_SUAVE, labelsize=8)


def _figura_para_base64(fig) -> str:
    """
    Serializa uma figura Matplotlib em ``data:image/png;base64,...``.

    TRANSPARÊNCIA TÉCNICA: o PNG é escrito em ``BytesIO`` (nunca em disco) e a
    figura é fechada em seguida para liberar memória — um relatório com 4
    gráficos não deve acumular 4 figuras abertas até o fim do processo.
    """
    buffer = io.BytesIO()
    fig.savefig(buffer, format="png", bbox_inches="tight", facecolor="white")
    plt = _pyplot()
    plt.close(fig)
    dados = base64.b64encode(buffer.getvalue()).decode("ascii")
    buffer.close()
    return f"data:image/png;base64,{dados}"


def _grafico_fluxo_caixa(anos, acumulados, payback) -> str:
    """
    G1 — fluxo de caixa acumulado por ano, com linha do zero e marcação do payback.

    TRANSPARÊNCIA TÉCNICA: a marca do payback é posicionada no primeiro ano cujo
    acumulado é não negativo; quando o investimento não cruza o zero no
    horizonte, nenhuma anotação é desenhada (o texto de aviso fica na seção).
    """
    plt = _pyplot()
    fig, ax = plt.subplots(figsize=(9, 3.5), dpi=110)
    ax.axhline(0.0, color="#8A949E", linewidth=1.0, linestyle="--", zorder=1)
    ax.plot(
        anos,
        acumulados,
        color=_ACCENT,
        linewidth=2.0,
        marker="o",
        markersize=4.5,
        zorder=3,
        label="Fluxo de caixa acumulado",
    )
    if payback is not None and math.isfinite(float(payback)):
        ax.axvline(
            float(payback),
            color=_COR_POSITIVO,
            linewidth=1.2,
            linestyle=":",
            zorder=2,
            label=f"Payback ≈ {_fmt_num(payback, 1)} anos",
        )
    cruzamento = None
    for indice, valor in enumerate(acumulados):
        if valor >= 0.0:
            cruzamento = indice
            break
    if cruzamento is not None:
        ax.annotate(
            f"Payback: ano {anos[cruzamento]}",
            xy=(anos[cruzamento], acumulados[cruzamento]),
            xytext=(8, 14),
            textcoords="offset points",
            fontsize=8,
            color=_COR_POSITIVO,
            arrowprops={"arrowstyle": "->", "color": _COR_POSITIVO, "linewidth": 0.9},
        )
    ax.set_title("Fluxo de caixa acumulado por ano", fontsize=10, color=_TEXTO)
    ax.set_xlabel("Ano", fontsize=8.5, color=_TEXTO_SUAVE)
    ax.set_ylabel("Acumulado (R$)", fontsize=8.5, color=_TEXTO_SUAVE)
    _estilo_eixos(ax)
    ax.legend(fontsize=7.5, frameon=False, loc="best")
    fig.tight_layout()
    return _figura_para_base64(fig)


def _grafico_dre(receita_energia: float, receita_demanda: float) -> str:
    """
    G2 — barras da DRE anual (receita de energia × receita de demanda).

    TRANSPARÊNCIA TÉCNICA: valores absolutos em R$/ano; rótulos com cifrão e
    separador pt-BR. Barras negativas (cenário economicamente adverso) são
    desenhadas abaixo do zero, sem truncamento.
    """
    plt = _pyplot()
    fig, ax = plt.subplots(figsize=(9, 3.5), dpi=110)
    rotulos = ["Receita de energia", "Receita de demanda"]
    valores = [receita_energia, receita_demanda]
    cores = [_ACCENT, "#3D8BC9"]
    barras = ax.bar(rotulos, valores, color=cores, width=0.5, zorder=3)
    for barra, valor in zip(barras, valores):
        altura = barra.get_height()
        deslocamento = 3 if altura >= 0 else -12
        ax.annotate(
            _fmt_brl(valor),
            xy=(barra.get_x() + barra.get_width() / 2.0, altura),
            xytext=(0, deslocamento),
            textcoords="offset points",
            ha="center",
            fontsize=8,
            color=_TEXTO,
        )
    ax.axhline(0.0, color="#8A949E", linewidth=0.9)
    ax.set_title("DRE anual — receitas por origem", fontsize=10, color=_TEXTO)
    ax.set_ylabel("R$ por ano", fontsize=8.5, color=_TEXTO_SUAVE)
    _estilo_eixos(ax)
    fig.tight_layout()
    return _figura_para_base64(fig)


def _grafico_perfil(perfil_base, perfil_bess, horas_ponta) -> str:
    """
    G3 — perfil horário de compra de energia: caso base × com BESS.

    TRANSPARÊNCIA TÉCNICA: eixo X fixo em 0–23 horas; a janela de ponta é
    sombreada em cinza claro. Séries vazias ou de tamanhos diferentes não são
    interpoladas — cada linha usa suas próprias abscissas.
    """
    plt = _pyplot()
    fig, ax = plt.subplots(figsize=(9, 3.5), dpi=110)
    if horas_ponta:
        horas_ordenadas = sorted(horas_ponta)
        ax.axvspan(
            min(horas_ordenadas) - 0.5,
            max(horas_ordenadas) + 0.5,
            color=_CINZA_PONTA,
            alpha=0.6,
            zorder=0,
            label="Janela de ponta",
        )
    if perfil_base:
        ax.plot(
            range(len(perfil_base)),
            perfil_base,
            color=_COR_BASE,
            linewidth=1.8,
            marker="o",
            markersize=3.5,
            zorder=3,
            label="Caso base",
        )
    if perfil_bess:
        ax.plot(
            range(len(perfil_bess)),
            perfil_bess,
            color=_COR_BESS,
            linewidth=1.8,
            marker="s",
            markersize=3.5,
            zorder=4,
            label="Com BESS",
        )
    ax.set_title("Compra de energia por hora — caso base × BESS", fontsize=10, color=_TEXTO)
    ax.set_xlabel("Hora do dia", fontsize=8.5, color=_TEXTO_SUAVE)
    ax.set_ylabel("Energia comprada (kWh)", fontsize=8.5, color=_TEXTO_SUAVE)
    ax.set_xlim(-0.5, 23.5)
    marcas = list(range(0, 24, 2))
    ax.set_xticks(marcas)
    ax.set_xticklabels([str(hora) for hora in marcas])
    _estilo_eixos(ax)
    ax.legend(fontsize=7.5, frameon=False, loc="best")
    fig.tight_layout()
    return _figura_para_base64(fig)


def _grafico_profundidades(pares) -> str:
    """
    G4 — profundidade de afundamento por barra: antes × depois.

    TRANSPARÊNCIA TÉCNICA: ``pares`` é uma lista de ``(barra, antes, depois)``
    já filtrada (barras com profundidade > 0 em ao menos um lado). Barras são
    agrupadas; a série "depois" usa a cor de destaque do relatório.
    """
    plt = _pyplot()
    fig, ax = plt.subplots(figsize=(9, 3.5), dpi=110)
    nomes = [par[0] for par in pares]
    antes = [par[1] for par in pares]
    depois = [par[2] for par in pares]
    posicoes = list(range(len(nomes)))
    largura = 0.38
    ax.bar(
        [pos - largura / 2.0 for pos in posicoes],
        antes,
        width=largura,
        color=_COR_BASE,
        zorder=3,
        label="Antes (caso base)",
    )
    ax.bar(
        [pos + largura / 2.0 for pos in posicoes],
        depois,
        width=largura,
        color=_COR_BESS,
        zorder=3,
        label="Depois (com BESS)",
    )
    ax.set_title("Profundidade de afundamento por barra (pu)", fontsize=10, color=_TEXTO)
    ax.set_ylabel("Profundidade (pu)", fontsize=8.5, color=_TEXTO_SUAVE)
    ax.set_xticks(posicoes)
    ax.set_xticklabels(nomes, rotation=45, ha="right", fontsize=7.5)
    _estilo_eixos(ax)
    ax.legend(fontsize=7.5, frameon=False, loc="best")
    fig.tight_layout()
    return _figura_para_base64(fig)


# ---------------------------------------------------------------------------
# Blocos HTML
# ---------------------------------------------------------------------------

_CSS = f"""
:root {{
    --accent: {_ACCENT};
    --borda: {_BORDA};
    --zebra: {_ZEBRA};
    --texto: {_TEXTO};
    --texto-suave: {_TEXTO_SUAVE};
}}
* {{ box-sizing: border-box; }}
body {{
    margin: 0;
    padding: 28px 32px 56px 32px;
    background: #FFFFFF;
    color: var(--texto);
    font-family: "Segoe UI", Calibri, "Trebuchet MS", Arial, sans-serif;
    font-size: 13.5px;
    line-height: 1.55;
}}
h1 {{
    font-size: 21px;
    color: var(--accent);
    margin: 0 0 4px 0;
    letter-spacing: 0.2px;
}}
h2 {{
    font-size: 15.5px;
    color: var(--accent);
    margin: 34px 0 10px 0;
    padding-bottom: 6px;
    border-bottom: 1px solid var(--borda);
}}
h3 {{ font-size: 13.5px; color: var(--texto); margin: 18px 0 8px 0; }}
p {{ margin: 0 0 10px 0; }}
.subtitulo {{ color: var(--texto-suave); font-size: 12.5px; margin: 0 0 16px 0; }}
.meta {{ color: var(--texto-suave); font-size: 12px; margin: 0 0 2px 0; }}
.cards {{
    display: flex;
    flex-wrap: wrap;
    gap: 12px;
    margin: 16px 0 4px 0;
}}
.card {{
    flex: 1 1 190px;
    min-width: 190px;
    border: 1px solid var(--borda);
    border-top: 3px solid var(--accent);
    border-radius: 6px;
    padding: 12px 14px;
    background: #FFFFFF;
}}
.card .rotulo {{
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    color: var(--texto-suave);
    margin-bottom: 6px;
}}
.card .valor {{ font-size: 19px; font-weight: 600; color: var(--accent); }}
.card .detalhe {{ font-size: 11.5px; color: var(--texto-suave); margin-top: 4px; }}
table {{
    width: 100%;
    border-collapse: collapse;
    margin: 10px 0 12px 0;
    font-size: 12.5px;
}}
thead th {{
    background: var(--accent);
    color: #FFFFFF;
    text-align: left;
    padding: 8px 10px;
    font-weight: 600;
    font-size: 12px;
}}
tbody td {{ padding: 7px 10px; border-bottom: 1px solid var(--borda); }}
tbody tr:nth-child(even) {{ background: var(--zebra); }}
td.num, th.num {{ text-align: right; font-variant-numeric: tabular-nums; }}
tr.destaque td {{ background: #E8F3EA !important; font-weight: 600; }}
tr.total td {{
    font-weight: 600;
    border-top: 2px solid var(--accent);
    background: #F0F4F8 !important;
}}
.nota {{
    background: var(--zebra);
    border-left: 3px solid var(--borda);
    padding: 9px 12px;
    font-size: 11.8px;
    color: var(--texto-suave);
    margin: 8px 0 14px 0;
}}
.grafico {{ margin: 12px 0 6px 0; }}
.grafico img {{ width: 100%; max-width: 960px; height: auto; display: block; }}
.legenda-grafico {{
    font-size: 11.5px;
    color: var(--texto-suave);
    margin: 0 0 16px 0;
}}
ul.lista {{ margin: 6px 0 14px 20px; padding: 0; }}
ul.lista li {{ margin-bottom: 6px; }}
.bloco-antes-depois {{
    display: flex;
    flex-wrap: wrap;
    gap: 16px;
    margin: 6px 0 12px 0;
}}
.coluna-lista {{ flex: 1 1 260px; }}
.coluna-lista .titulo {{ font-size: 12px; font-weight: 600; margin-bottom: 4px; }}
.chips {{ display: flex; flex-wrap: wrap; gap: 6px; }}
.chip {{
    display: inline-block;
    border: 1px solid var(--borda);
    border-radius: 12px;
    padding: 2px 9px;
    font-size: 11.5px;
    background: var(--zebra);
    color: var(--texto);
}}
.aviso {{ color: var(--texto-suave); font-size: 12px; font-style: italic; }}
.alertas {{ display: flex; flex-direction: column; gap: 10px; margin: 10px 0 6px 0; }}
.alerta {{
    border: 1px solid {_AMBAR_BORDA};
    background: {_AMBAR_BG};
    border-left: 4px solid {_AMBAR_BORDA};
    border-radius: 5px;
    padding: 11px 14px;
    font-size: 12.5px;
}}
.alerta .titulo {{ font-weight: 600; margin-bottom: 4px; display: block; }}
.ok {{
    border: 1px solid {_VERDE_BORDA};
    background: {_VERDE_BG};
    border-left: 4px solid {_VERDE_BORDA};
    border-radius: 5px;
    padding: 11px 14px;
    font-size: 12.5px;
}}
.incentivo {{
    border: 1px solid var(--borda);
    border-left: 3px solid var(--accent);
    border-radius: 5px;
    padding: 11px 14px;
    margin-bottom: 10px;
}}
.incentivo .titulo {{ font-weight: 600; color: var(--accent); margin-bottom: 5px; }}
.incentivo .fonte {{ font-size: 11.5px; color: var(--texto-suave); margin-top: 5px; }}
.incentivo .nota-item {{ font-size: 11.5px; color: #8A6D00; margin-top: 3px; }}
.premissas {{ font-size: 11.8px; color: var(--texto-suave); }}
.premissas li {{ margin-bottom: 5px; }}
.rodape {{
    margin-top: 30px;
    padding-top: 14px;
    border-top: 1px solid var(--borda);
    font-size: 11px;
    color: var(--texto-suave);
}}
code {{ font-family: Consolas, "Courier New", monospace; font-size: 11.5px; }}
"""


def _secao_cabecalho(dados: dict) -> str:
    """
    Seção 1 — cabeçalho executivo com identificação e resumo do estudo.

    TRANSPARÊNCIA TÉCNICA: nenhum dado derivado é inventado; campos ausentes
    aparecem como ``—``.
    """
    return f"""
<h1>Justificativa de Investimento — Sistema de Armazenamento de Energia (BESS)</h1>
<p class="subtitulo">Estudo de otimização de alocação e dimensionamento de BESS com avaliação econômica e de qualidade de energia.</p>
<p class="meta"><strong>Projeto:</strong> {_escapar(dados["nome_projeto"])}</p>
<p class="meta"><strong>Gerado em:</strong> {_escapar(dados["carimbo"])}</p>
<p class="meta"><strong>Tarifa:</strong> {_escapar(dados["tarifa_nome"])} — modalidade {_escapar(dados["tarifa_modalidade"])}</p>
<p class="meta"><strong>Pesos do estudo:</strong> qualidade {_escapar(dados["peso_qualidade"])} · economia {_escapar(dados["peso_economia"])} · custo {_escapar(dados["peso_custo"])}</p>
<p class="meta"><strong>Status do MILP:</strong> {_escapar(dados["status_milp"])}</p>
"""


def _secao_cartoes(dados: dict) -> str:
    """
    Seção 2 — seis cartões executivos (CAPEX, receita, payback, ROI, sag, severidade).
    """
    return f"""
<h2>Resumo executivo</h2>
<div class="cards">
    <div class="card">
        <div class="rotulo">CAPEX</div>
        <div class="valor">{_fmt_brl(dados["capex"])}</div>
        <div class="detalhe">{dados["n_selecionados"]} modelo(s) BESS selecionado(s)</div>
    </div>
    <div class="card">
        <div class="rotulo">Receita anual</div>
        <div class="valor">{_fmt_brl(dados["receita_total_anual"])}</div>
        <div class="detalhe">Energia {_fmt_brl(dados["receita_energia"])} + demanda {_fmt_brl(dados["receita_demanda"])}</div>
    </div>
    <div class="card">
        <div class="rotulo">Payback</div>
        <div class="valor">{_fmt_anos(dados["payback_anos"])}</div>
        <div class="detalhe">CAPEX ÷ receita anual total</div>
    </div>
    <div class="card">
        <div class="rotulo">ROI anual</div>
        <div class="valor">{_fmt_pct(dados["roi_anual_pct"])}</div>
        <div class="detalhe">Receita anual ÷ CAPEX</div>
    </div>
    <div class="card">
        <div class="rotulo">Barras em sag</div>
        <div class="valor">{dados["sag_antes"]} → {dados["sag_depois"]}</div>
        <div class="detalhe">Antes → depois da alocação</div>
    </div>
    <div class="card">
        <div class="rotulo">Redução média de severidade</div>
        <div class="valor">{_fmt_pct(dados["reducao_severidade_pct"])}</div>
        <div class="detalhe">Soma das profundidades por barra</div>
    </div>
</div>
"""


def _secao_dre(dados: dict) -> str:
    """
    Seção 3 — DRE anual simplificada (sem O&M) com nota fixa de limitações.

    TRANSPARÊNCIA TÉCNICA: a linha "RESULTADO ECONÔMICO ANUAL" é igual à receita
    total porque O&M e degradação não são modelados; a nota sob a tabela torna
    a omissão explícita ao leitor, em vez de deixá-la implícita.
    """
    return f"""
<h2>DRE anual — justificativa de investimento</h2>
<table>
    <thead>
        <tr><th>Linha</th><th class="num">Valor</th></tr>
    </thead>
    <tbody>
        <tr><td>Receita anual de energia</td><td class="num">{_fmt_brl(dados["receita_energia"])}</td></tr>
        <tr><td>Receita anual de demanda</td><td class="num">{_fmt_brl(dados["receita_demanda"])}</td></tr>
        <tr class="total"><td>RECEITA TOTAL</td><td class="num">{_fmt_brl(dados["receita_total_anual"])}</td></tr>
        <tr><td>INVESTIMENTO (CAPEX)</td><td class="num">{_fmt_brl(dados["capex"])}</td></tr>
        <tr class="total"><td>RESULTADO ECONÔMICO ANUAL</td><td class="num">{_fmt_brl(dados["receita_total_anual"])}</td></tr>
        <tr><td>Payback simples</td><td class="num">{_fmt_anos(dados["payback_anos"])}</td></tr>
        <tr><td>ROI anual</td><td class="num">{_fmt_pct(dados["roi_anual_pct"])}</td></tr>
    </tbody>
</table>
<div class="nota">{_escapar(_NOTA_DRE)}</div>
"""


def _secao_projecao(dados: dict) -> tuple:
    """
    Seção 4 — projeção multi-anual do fluxo de caixa.

    Returns:
        ``(html_tabela, serie_acumulados, anos, payback)`` — os três últimos
        alimentam o gráfico G1.

    TRANSPARÊNCIA TÉCNICA: premissa de receita anual constante (tarifa e perfil
    representativo invariantes no horizonte). A primeira linha com acumulado não
    negativo é destacada; quando não há cruzamento, o relatório declara a
    ausência explicitamente.
    """
    receita = dados["receita_total_anual"]
    capex = dados["capex"]
    payback = dados["payback_anos"]
    horizonte = _horizonte_projecao(payback)

    anos = [0]
    acumulados = [-capex]
    linhas = [
        "<tr><td>0</td>"
        f"<td class=\"num\">{_fmt_brl(0.0)}</td>"
        f"<td class=\"num\">{_fmt_brl(-capex)}</td></tr>"
    ]
    acumulado = -capex
    primeiro_positivo = None
    for ano in range(1, horizonte + 1):
        acumulado += receita
        anos.append(ano)
        acumulados.append(acumulado)
        if primeiro_positivo is None and acumulado >= 0.0:
            primeiro_positivo = ano
        classe = ' class="destaque"' if (primeiro_positivo == ano) else ""
        linhas.append(
            f"<tr{classe}><td>{ano}</td>"
            f"<td class=\"num\">{_fmt_brl(receita)}</td>"
            f"<td class=\"num\">{_fmt_brl(acumulado)}</td></tr>"
        )

    aviso = ""
    if primeiro_positivo is None:
        aviso = (
            '<div class="nota">O investimento não se paga no horizonte projetado.</div>'
        )

    html = f"""
<h2>Projeção multi-anual do fluxo de caixa</h2>
<p class="legenda-grafico">Horizonte de {horizonte} anos com receita anual constante de {_fmt_brl(receita)} (premissa: tarifa e perfil representativo invariantes).</p>
<table>
    <thead>
        <tr><th>Ano</th><th class="num">Receita do ano</th><th class="num">Fluxo acumulado</th></tr>
    </thead>
    <tbody>
        {''.join(linhas)}
    </tbody>
</table>
{aviso}
"""
    return html, acumulados, anos, payback


def _secao_graficos(dados: dict, acumulados: list, anos: list) -> str:
    """
    Seção 5 — quatro gráficos embutidos como PNG base64.

    TRANSPARÊNCIA TÉCNICA: cada gráfico é gerado sob demanda e degrada para um
    aviso textual quando os dados de origem estão ausentes (perfil vazio,
    nenhuma barra com profundidade > 0). O relatório nunca quebra por falta de
    dados de um gráfico específico.
    """
    blocos = []

    blocos.append(
        '<div class="grafico">'
        f'<img alt="Fluxo de caixa acumulado por ano" src="{_grafico_fluxo_caixa(anos, acumulados, dados["payback_anos"])}">'
        "</div>"
        '<p class="legenda-grafico">G1 — Fluxo de caixa acumulado por ano (R$). A linha tracejada marca o zero; o ponto destacado indica o primeiro ano com acumulado não negativo.</p>'
    )

    blocos.append(
        '<div class="grafico">'
        f'<img alt="DRE anual por origem de receita" src="{_grafico_dre(dados["receita_energia"], dados["receita_demanda"])}">'
        "</div>"
        '<p class="legenda-grafico">G2 — Receita anual por origem: energia deslocada no tempo × redução de demanda na ponta (R$/ano).</p>'
    )

    perfil_base = dados["perfil_base"]
    perfil_bess = dados["perfil_bess"]
    if perfil_base or perfil_bess:
        blocos.append(
            '<div class="grafico">'
            f'<img alt="Perfil horário de compra de energia: caso base e com BESS" src="{_grafico_perfil(perfil_base, perfil_bess, dados["horas_ponta"])}">'
            "</div>"
            '<p class="legenda-grafico">G3 — Energia comprada por hora (kWh), dia representativo. Faixa cinza: janela de ponta.</p>'
        )
    else:
        blocos.append(
            '<p class="aviso">G3 — Perfil horário indisponível no resultado do estudo.</p>'
        )

    pares = dados["pares_profundidade"]
    if pares:
        blocos.append(
            '<div class="grafico">'
            f'<img alt="Profundidade de afundamento por barra antes e depois" src="{_grafico_profundidades(pares)}">'
            "</div>"
            '<p class="legenda-grafico">G4 — Profundidade de afundamento por barra (pu), caso base × com BESS. Apenas barras com profundidade > 0 em ao menos um cenário.</p>'
        )
    else:
        blocos.append(
            '<p class="aviso">G4 — Nenhuma barra apresentou profundidade de afundamento registrada.</p>'
        )

    return '<h2>Gráficos</h2>\n' + "\n".join(blocos)


def _chips(barras) -> str:
    """
    Renderiza uma lista de nomes de barra como chips HTML.

    TRANSPARÊNCIA TÉCNICA: lista vazia vira aviso textual explícito.
    """
    if not barras:
        return '<span class="aviso">Nenhuma barra nesta condição.</span>'
    itens = "".join(f'<span class="chip">{_escapar(nome)}</span>' for nome in barras)
    return f'<div class="chips">{itens}</div>'


def _secao_qualidade(dados: dict) -> str:
    """
    Seção 6 — qualidade de energia: barras em sag, profundidades, FP e diferenciais.

    TRANSPARÊNCIA TÉCNICA: a tabela de profundidades mostra reduzir/majorar por
    barra e a redução percentual relativa; quando o valor de base é zero, a
    redução relativa é indefinida e aparece como ``—`` (divisão por zero não é
    mascarada).
    """
    linhas = []
    for barra, antes, depois in dados["pares_profundidade"]:
        if antes > 0.0:
            reducao = (1.0 - depois / antes) * 100.0
            reducao_txt = _fmt_pct(reducao)
        else:
            reducao_txt = "—"
        linhas.append(
            f"<tr><td>{_escapar(barra)}</td>"
            f'<td class="num">{_fmt_num(antes, 4)}</td>'
            f'<td class="num">{_fmt_num(depois, 4)}</td>'
            f'<td class="num">{reducao_txt}</td></tr>'
        )
    tabela = ""
    if linhas:
        tabela = f"""
<h3>Profundidade de afundamento por barra</h3>
<table>
    <thead>
        <tr><th>Barra</th><th class="num">Antes (pu)</th><th class="num">Depois (pu)</th><th class="num">Redução</th></tr>
    </thead>
    <tbody>
        {''.join(linhas)}
    </tbody>
</table>
"""
    else:
        tabela = '<p class="aviso">Nenhuma barra apresentou profundidade de afundamento registrada em nenhum dos cenários.</p>'

    return f"""
<h2>Qualidade de energia</h2>
<div class="bloco-antes-depois">
    <div class="coluna-lista">
        <div class="titulo">Barras em sag — antes ({len(dados["barras_sag_antes"])})</div>
        {_chips(dados["barras_sag_antes"])}
    </div>
    <div class="coluna-lista">
        <div class="titulo">Barras em sag — depois ({len(dados["barras_sag_depois"])})</div>
        {_chips(dados["barras_sag_depois"])}
    </div>
</div>
{tabela}
<h3>Fator de potência</h3>
<p>{_escapar(dados["texto_fator_potencia"])}</p>
<h3>Diferenciais metodológicos</h3>
<ul class="lista">
    <li><strong>Métrica contínua de severidade:</strong> a avaliação usa a profundidade do afundamento como grandeza contínua, creditando melhoras parciais que uma métrica binária (barra em sag / fora de sag) zeraria.</li>
    <li><strong>Verificação conjunta:</strong> o benefício é apurado sobre o conjunto completo de faltas, com o BESS despachando segundo o próprio estado de carga — apurando o benefício real, não o benefício teórico de cada falta isolada.</li>
    <li><strong>Cenários não convergentes:</strong> faltas cujo fluxo de potência não converge são tratadas como colapso de tensão e nunca creditadas como benefício ao BESS.</li>
</ul>
"""


def _secao_alertas(dados: dict) -> str:
    """
    Seção 7 — alertas operacionais/econômicos do estudo.

    TRANSPARÊNCIA TÉCNICA: o alerta de exportação é emitido tanto pelo
    sinalizador do estudo quanto pela existência de volume exportado > 0; a
    ordem dos cartões segue a gravidade (superdimensionamento, exportação).
    """
    cartoes = []
    if dados["alerta_superdimensionamento"]:
        cartoes.append(
            '<div class="alerta">'
            '<span class="titulo">Possível superdimensionamento do BESS</span>'
            "A capacidade selecionada excede o necessário para o perfil avaliado: os "
            "benefícios marginais de redução de custo não acompanham o acréscimo de "
            "CAPEX. Revisar limites do catálogo e restrições de investimento antes da "
            "decisão final."
            "</div>"
        )
    if dados["alerta_caso_base_exportacao"]:
        cartoes.append(
            '<div class="alerta">'
            '<span class="titulo">Caso base com exportação à rede</span>'
            "O caso base já exporta energia para a rede. O relatório não monetiza "
            "energia exportada, de modo que a receita apurada é conservadora e o "
            "payback tende a ser superestimado. Verificar a regra de compensação "
            "aplicável ao ponto de conexão."
            "</div>"
        )
    elif dados["total_exportado_kwh"] > 0.0:
        cartoes.append(
            '<div class="alerta">'
            '<span class="titulo">Energia exportada não monetizada</span>'
            f"O cenário com BESS exporta {_fmt_num(dados['total_exportado_kwh'], 2)} kWh "
            "no dia representativo. Esse volume não é convertido em receita neste "
            "relatório — o retorno apurado é conservador."
            "</div>"
        )
    if not cartoes:
        cartoes.append(
            '<div class="ok"><strong>Sem alertas.</strong> O estudo não sinalizou '
            "superdimensionamento nem exportação relevante no caso base.</div>"
        )
    return '<h2>Alertas</h2>\n<div class="alertas">\n' + "\n".join(cartoes) + "\n</div>\n"


def _secao_incentivos() -> str:
    """
    Seção 8 — panorama de incentivos regulatórios (conteúdo estático).

    TRANSPARÊNCIA TÉCNICA: os itens vêm de ``INCENTIVOS_PADRAO``; cada um traz
    fonte e nota própria de verificação, e a seção fecha com a ressalva de
    conferência em fontes oficiais.
    """
    blocos = []
    for item in INCENTIVOS_PADRAO:
        blocos.append(
            '<div class="incentivo">'
            f'<div class="titulo">{_escapar(item["titulo"])}</div>'
            f'<div>{_escapar(item["descricao"])}</div>'
            f'<div class="fonte"><strong>Fonte:</strong> {_escapar(item["fonte"])}</div>'
            f'<div class="nota-item"><strong>Nota:</strong> {_escapar(item["nota"])}</div>'
            "</div>"
        )
    return (
        "<h2>Incentivos e instrumentos regulatórios</h2>\n"
        + "\n".join(blocos)
        + '\n<div class="nota">Confirmar vigência e condições nas fontes oficiais antes do uso executivo.</div>\n'
    )


def _secao_rodape(dados: dict) -> str:
    """
    Seção 9 — premissas, fonte tarifária, caminho do arquivo e carimbo.

    TRANSPARÊNCIA TÉCNICA: a fórmula de recomposição tributária da tarifa é
    reproduzida literalmente porque o estudo econômico usa a tarifa homologada
    sem tributos; sem isso, o leitor não consegue reconciliar a receita apurada
    com a fatura real.
    """
    return f"""
<h2>Premissas e metodologia</h2>
<ul class="lista premissas">
    <li><strong>Dia representativo quase-estático:</strong> o perfil de 24 horas é tratado como dia típico; a receita anual é extrapolada pela economia diária projetada ao período de análise.</li>
    <li><strong>Despacho por estado de carga:</strong> a operação do BESS respeita a janela de SoC de 0,20 a 0,95 em cada passo horário.</li>
    <li><strong>Sem O&amp;M e sem degradação:</strong> custos de operação, manutenção e perda de capacidade da bateria não são modelados; a energia exportada não é monetizada.</li>
    <li><strong>Tarifa sem tributos:</strong> os valores usados seguem a fonte informada e não embutem tributos. Recomposição utilizada no estudo: <code>Tarifa final = Tarifa homologada / [(100−PIS−COFINS)/100] / [(100−ICMS)/100]</code>.</li>
</ul>
<p class="meta"><strong>Fonte da tarifa:</strong> {_escapar(dados["tarifa_nome"])} — modalidade {_escapar(dados["tarifa_modalidade"])}</p>
<p class="meta"><strong>Arquivo:</strong> {_escapar(dados["caminho_saida"])}</p>
<div class="rodape">
    <div>Relatório gerado automaticamente pelo módulo <code>otimizacao_exportar_roi</code> — {_escapar(dados["carimbo"])}</div>
    <div>{_escapar(__author__)}</div>
</div>
"""


# ---------------------------------------------------------------------------
# Conteúdo estático de incentivos
# ---------------------------------------------------------------------------

INCENTIVOS_PADRAO = [
    {
        "titulo": "Lei nº 15.269/2025 — marco regulatório do armazenamento",
        "descricao": (
            "Conversão da MP 1.304/2025, sancionada em 25/11/2025 com vetos: reconhece o "
            "armazenamento de energia no setor elétrico (inclusive sistemas atrás do medidor) "
            "e estende o REIDI — regime especial de redução de PIS/COFINS — às instalações de "
            "armazenamento."
        ),
        "fonte": "Lei nº 15.269/2025 — planalto.gov.br",
        "nota": "Confirmar vigência, vetos e regulamentação nas fontes oficiais.",
    },
    {
        "titulo": "Primeiro leilão exclusivo de armazenamento por baterias",
        "descricao": (
            "A Portaria MME nº 136 estabeleceu as diretrizes do primeiro leilão exclusivo de "
            "baterias do Brasil, com leilões previstos para dezembro/2026 e ciclo de leilões de "
            "armazenamento entre 2027 e 2029 — sinal de mercado para serviços prestados por BESS."
        ),
        "fonte": "Ministério de Minas e Energia — gov.br/mme (Portaria MME nº 136)",
        "nota": "Acompanhar os editais da ANEEL para condições de participação.",
    },
    {
        "titulo": "Programas de P&D regulados pela ANEEL",
        "descricao": (
            "Projetos de P&D com distribuidoras já financiaram projetos-piloto de armazenamento "
            "por baterias no país — via de acesso a financiamento parcial de projetos "
            "demonstrativos."
        ),
        "fonte": "ANEEL — gov.br/aneel",
        "nota": "Edições e chamadas variam por ano.",
    },
    {
        "titulo": "Incentivos estaduais e programas de distribuidoras",
        "descricao": (
            "Benefícios fiscais estaduais (ICMS) e programas próprios de concessionárias variam "
            "por unidade federativa."
        ),
        "fonte": "Concessionária local (no estudo de referência: CELESC)",
        "nota": "Verificar a distribuidora do ponto de conexão.",
    },
]


# ---------------------------------------------------------------------------
# Montagem do documento
# ---------------------------------------------------------------------------


def _extrair_dados(
    resultado: dict,
    caminho_saida: str,
    nome_projeto,
    limite_superior: float,
) -> dict:
    """
    Normaliza o ``resultado`` do estudo em um dicionário de apresentação.

    TRANSPARÊNCIA TÉCNICA: todo valor numérico consumido pelas seções passa por
    ``float()``/``int()``/``bool()`` aqui; as seções seguintes não precisam
    repetir conversões nem lidar com ``numpy``.
    """
    economia = resultado.get("resultado_economia") or {}
    selecionados = list(resultado.get("selecionados") or [])
    pesos = resultado.get("pesos_criterio") or {}
    reativo = resultado.get("analise_reativo") or {}
    baseline = resultado.get("resultado_baseline") or {}
    conjunto = resultado.get("resultado_conjunto") or {}

    tarifa = economia.get("tarifa")
    tarifa_nome = "—"
    tarifa_modalidade = "—"
    if isinstance(tarifa, dict):
        tarifa_nome = tarifa.get("nome") or "—"
        tarifa_modalidade = tarifa.get("modalidade") or "—"
    elif tarifa is not None:
        tarifa_nome = getattr(tarifa, "nome", "—") or "—"
        tarifa_modalidade = getattr(tarifa, "modalidade", "—") or "—"

    capex = _capital_bess(selecionados)
    receita_energia = _to_float(economia.get("economia_anual"), 0.0)
    receita_demanda = _to_float(economia.get("economia_demanda_mensal_estimada"), 0.0) * 12.0
    receita_total = receita_energia + receita_demanda

    if capex > 0.0:
        roi_anual = receita_total / capex * 100.0
    else:
        roi_anual = None

    payback_declarado = _to_opt_float(economia.get("payback_anos"))
    if payback_declarado is not None:
        payback_final = payback_declarado
    elif capex > 0.0 and receita_total > 0.0:
        payback_final = capex / receita_total
    else:
        payback_final = None

    prof_antes = _profundidades_seguras(baseline, limite_superior)
    prof_depois = _profundidades_seguras(conjunto, limite_superior)
    soma_antes = sum(prof_antes.values())
    soma_depois = sum(prof_depois.values())
    if soma_antes > 0.0:
        reducao_severidade = (1.0 - soma_depois / soma_antes) * 100.0
    else:
        reducao_severidade = None

    todas_barras = _ordena_barras(set(prof_antes) | set(prof_depois))
    pares = []
    for barra in todas_barras:
        antes = prof_antes.get(barra, 0.0)
        depois = prof_depois.get(barra, 0.0)
        if antes > 0.0 or depois > 0.0:
            pares.append((barra, antes, depois))

    barras_sag_antes = _ordena_barras(resultado.get("barras_em_sag_baseline") or [])
    barras_sag_depois = _ordena_barras(baseline.get("barras_em_sag_geral") or [])
    barras_sag_depois_conjunto = _ordena_barras(conjunto.get("barras_em_sag_geral") or [])

    fp_valor = _to_opt_float(reativo.get("fator_potencia"))
    fp_minimo = _to_opt_float(reativo.get("fp_minimo_referencia"))
    conforme = _to_bool(reativo.get("conforme"))
    if conforme:
        texto_fp = (
            "Conforme — compensação dispensada"
            + (f" (fator de potência {_fmt_num(fp_valor, 3)}" if fp_valor is not None else "")
            + (f"; mínimo de referência {_fmt_num(fp_minimo, 3)})." if fp_minimo is not None else (")." if fp_valor is not None else ""))
        )
    else:
        recomendacao = reativo.get("recomendacao") or ""
        if recomendacao:
            texto_fp = str(recomendacao)
        elif fp_valor is not None:
            texto_fp = (
                f"Fator de potência {_fmt_num(fp_valor, 3)} abaixo da referência"
                + (f" de {_fmt_num(fp_minimo, 3)}" if fp_minimo is not None else "")
                + " — avaliar compensação reativa."
            )
        else:
            texto_fp = "Análise de reativo indisponível no resultado do estudo."

    perfil_base = _perfil_horario(economia.get("perfil_base"), "kw_comprada")
    perfil_bess = _perfil_horario(economia.get("perfil_bess"), "kw_comprada")
    horas_ponta = _horas_ponta(economia.get("perfil_base"))

    carimbo = _dt.datetime.now().strftime("%d/%m/%Y às %H:%M")

    return {
        "nome_projeto": nome_projeto or os.path.basename(str(caminho_saida)) or "Projeto",
        "caminho_saida": str(caminho_saida),
        "carimbo": carimbo,
        "tarifa_nome": str(tarifa_nome),
        "tarifa_modalidade": str(tarifa_modalidade),
        "peso_qualidade": _fmt_num(_to_float(pesos.get("peso_qualidade"), 0.0), 2),
        "peso_economia": _fmt_num(_to_float(pesos.get("peso_economia"), 0.0), 2),
        "peso_custo": _fmt_num(_to_float(pesos.get("peso_custo"), 0.0), 2),
        "status_milp": str(resultado.get("status_milp") or "não informado"),
        "n_selecionados": len(selecionados),
        "capex": capex,
        "receita_energia": receita_energia,
        "receita_demanda": receita_demanda,
        "receita_total_anual": receita_total,
        "payback_anos": payback_final,
        "roi_anual_pct": roi_anual,
        "sag_antes": len(barras_sag_antes),
        "sag_depois": len(barras_sag_depois_conjunto) if barras_sag_depois_conjunto else len(barras_sag_depois),
        "barras_sag_antes": barras_sag_antes,
        "barras_sag_depois": barras_sag_depois_conjunto or barras_sag_depois,
        "reducao_severidade_pct": reducao_severidade,
        "pares_profundidade": pares,
        "perfil_base": perfil_base,
        "perfil_bess": perfil_bess,
        "horas_ponta": horas_ponta,
        "texto_fator_potencia": texto_fp,
        "alerta_superdimensionamento": _to_bool(economia.get("alerta_superdimensionamento")),
        "alerta_caso_base_exportacao": _to_bool(economia.get("alerta_caso_base_exportacao")),
        "total_exportado_kwh": _to_float(economia.get("total_exportado_kwh_bess"), 0.0),
        "energia_ponta_base": _to_float(economia.get("energia_ponta_kwh_base"), 0.0),
        "energia_fora_base": _to_float(economia.get("energia_fora_ponta_kwh_base"), 0.0),
        "energia_ponta_bess": _to_float(economia.get("energia_ponta_kwh_bess"), 0.0),
        "energia_fora_bess": _to_float(economia.get("energia_fora_ponta_kwh_bess"), 0.0),
        "custo_diario_base": _to_float(economia.get("custo_diario_base"), 0.0),
        "custo_diario_bess": _to_float(economia.get("custo_diario_bess"), 0.0),
        "beneficio_conjunto_real": _to_int(resultado.get("beneficio_conjunto_real"), 0),
    }


def gerar_relatorio_roi(
    resultado: dict,
    caminho_saida: str,
    nome_projeto: str | None = None,
    limite_inferior: float = 0.1,
    limite_superior: float = 0.9,
) -> str:
    """
    Gera o relatório HTML de justificativa de investimento (ROI/DRE) do BESS.

    TRANSPARÊNCIA TÉCNICA
    ---------------------
    * Entrada: dicionário de ``otimizacao_bess.executar_estudo_completo``. O
      módulo não executa o estudo nem recalcula benefícios de qualidade — apenas
      apresenta a economia e as profundidades já apuradas.
    * A profundidade por barra é obtida de ``_profundidades_por_barra`` do motor,
      com ``limite_superior`` como limite de sensibilidade; ``limite_inferior`` é
      aceito por compatibilidade de assinatura com o motor (a métrica de
      profundidade não o utiliza).
    * Todos os valores numéricos são convertidos com ``float()``/``int()``/
      ``bool()`` — o motor devolve ``numpy.float64``.
    * Formatação pt-BR feita sem ``locale``; o locale do processo não é alterado.
    * Matplotlib em backend ``Agg``: nenhuma janela é aberta e nenhum arquivo
      intermediário é escrito em disco — os PNGs vão para memória e são
      embutidos como base64.
    * Saída: HTML5 standalone (UTF-8, CSS inline, sem JavaScript e sem CDN),
      gravado no caminho informado.

    Args:
        resultado: dicionário completo do estudo de otimização de BESS.
        caminho_saida: caminho do arquivo ``.html`` a ser gravado.
        nome_projeto: nome exibido no cabeçalho. Quando ``None``, usa o nome do
            arquivo de saída.
        limite_inferior: limite inferior de sensibilidade do afundamento
            (mantido por compatibilidade; não usado no cálculo da profundidade).
        limite_superior: limite superior de sensibilidade do afundamento,
            repassado a ``_profundidades_por_barra``.

    Returns:
        O caminho do arquivo gravado (o mesmo ``caminho_saida``).

    Raises:
        ValueError: se ``resultado`` não for um dicionário, se não contiver
            ``resultado_economia`` utilizável ou se ``selecionados`` estiver
            vazio.
        OSError: se o arquivo de saída não puder ser gravado.
    """
    if not isinstance(resultado, dict):
        raise ValueError(
            "Resultado inválido para o relatório de ROI: esperado dicionário com os "
            "campos do estudo de otimização de BESS."
        )
    economia = resultado.get("resultado_economia")
    if not isinstance(economia, dict) or not economia:
        raise ValueError(
            "Resultado sem 'resultado_economia': o relatório de ROI/DRE exige a "
            "avaliação econômica. Execute o estudo econômico antes de exportar."
        )
    selecionados = resultado.get("selecionados")
    if not selecionados:
        raise ValueError(
            "Nenhum BESS selecionado: não há investimento a justificar. Ajuste os "
            "critérios e restrições do estudo antes de exportar o relatório de ROI."
        )

    _ = float(limite_inferior)  # compatibilidade de assinatura; não usado aqui
    limite_sup = _to_float(limite_superior, 0.9)

    dados = _extrair_dados(resultado, caminho_saida, nome_projeto, limite_sup)

    html_projecao, acumulados, anos, _payback_grafico = _secao_projecao(dados)

    partes = [
        "<!DOCTYPE html>",
        '<html lang="pt-BR">',
        "<head>",
        '<meta charset="UTF-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1.0">',
        f"<title>Justificativa de Investimento — BESS — {_escapar(dados['nome_projeto'])}</title>",
        "<style>",
        _CSS,
        "</style>",
        "</head>",
        "<body>",
        _secao_cabecalho(dados),
        _secao_cartoes(dados),
        _secao_dre(dados),
        html_projecao,
        _secao_graficos(dados, acumulados, anos),
        _secao_qualidade(dados),
        _secao_alertas(dados),
        _secao_incentivos(),
        _secao_rodape(dados),
        "</body>",
        "</html>",
    ]
    documento = "\n".join(partes) + "\n"

    diretorio = os.path.dirname(os.path.abspath(str(caminho_saida)))
    if diretorio:
        os.makedirs(diretorio, exist_ok=True)
    with open(str(caminho_saida), "w", encoding="utf-8", newline="\n") as arquivo:
        arquivo.write(documento)

    return str(caminho_saida)
