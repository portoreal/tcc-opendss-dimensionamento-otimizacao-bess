__author__ = 'Pedro Henrique Sousa Pinheiro'
"""Exportador de gráficos da Simulação ao Vivo (headless, sem Qt).

Renderiza gráficos a partir do SNAPSHOT de
``SessaoAoVivo.dados_para_exportar()`` (ledger de passos + log de eventos +
perfis de carga por barra) e grava arquivos PNG/JPEG/SVG.

TRANSPARÊNCIA TÉCNICA:
1. Exporta o que foi SIMULADO: dias presentes no snapshot; passos não
   resolvidos não existem nos gráficos.
2. Nuvens e afundamentos aparecem como MARCAÇÕES (linhas verticais) nos
   gráficos que cobrem os passos correspondentes — o dado já contém o
   efeito físico; a marcação só aponta o instante.
3. JPEG não suporta transparência: fundo 'transparente' + jpeg grava com
   fundo branco e devolve aviso.
4. Sem PySide6: Figure + FigureCanvasAgg (matplotlib puro) — testável
   headless e reutilizável fora da janela.
5. Atuação do controlador = série de estados por BESS (repouso/
   carregando/descarregando) com eventos marcados — o gráfico essencial
   do painel.
6. Carga SEM curva no rede.json = constante (o fator do dia só edita
   LoadShapes) — o snapshot já reflete isso em cargas_por_barra.
"""

import os
from typing import Any, Dict, List, Tuple

from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
from matplotlib.lines import Line2D

CHAVES_GRAFICOS = {
    "cargas_barras": "Curvas de carga — por barra (kW)",
    "geracao_pv": "Geração PV — por unidade (kW)",
    "bess_soc": "BESS — nível de carga (SoC %)",
    "bess_potencia": "BESS — potência despachada (kW)",
    "bess_controlador": "BESS — atuação do controlador (com eventos)",
    "economia": "Economia acumulada (R$)",
    "tensao": "Tensão — Vmin/Vmax (pu)",
    "fonte_perdas": "Fonte e perdas (kW)",
}

CORES_ESTADO = {"repouso": "#9e9e9e", "carregando": "#1b8f3a",
                "descarregando": "#b35c00"}
NIVEL_ESTADO = {"repouso": 0, "carregando": 1, "descarregando": 2}
ROTULOS_ESTADO = ["Repouso", "Carregando", "Descarregando"]
CORES_EVENTO = {"afundamento": "#c62828", "nuvem": "#00838f",
                "virada_dia": "#666666", "tarifa": "#7b1fa2"}
COR_TEXTO_ESCURO = "#dddddd"


def _nova_figura(fundo: str) -> Tuple[Figure, Any]:
    fig = Figure(figsize=(8.0, 4.5), layout="constrained")
    FigureCanvasAgg(fig)
    if fundo == "escuro":
        fig.patch.set_facecolor("#1e1e1e")
    ax = fig.add_subplot(1, 1, 1)
    ax.grid(True, alpha=0.25, linewidth=0.6)
    return fig, ax


def _finalizar(fig, ax, fundo: str):
    for ax in (ax if isinstance(ax, (list, tuple)) else [ax]):
        _finalizar_eixo(fig, ax, fundo)


def _finalizar_eixo(fig, ax, fundo: str):
    if fundo == "escuro":
        ax.set_facecolor("#1e1e1e")
        ax.tick_params(colors=COR_TEXTO_ESCURO, labelcolor=COR_TEXTO_ESCURO)
        ax.title.set_color(COR_TEXTO_ESCURO)
        ax.xaxis.label.set_color(COR_TEXTO_ESCURO)
        ax.yaxis.label.set_color(COR_TEXTO_ESCURO)
        for spine in ax.spines.values():
            spine.set_color("#888888")
        legenda = ax.get_legend()
        if legenda:
            legenda.get_frame().set_facecolor("#2a2a2a")
            legenda.get_frame().set_edgecolor("#888888")
            for texto in legenda.get_texts():
                texto.set_color(COR_TEXTO_ESCURO)


def _gravar(fig, caminho: str, fundo: str, formato: str, avisos: List[str]):
    transparente = (fundo == "transparente")
    if transparente and formato == "jpeg":
        transparente = False
        avisos.append(f"{os.path.basename(caminho)}: fundo transparente "
                      "não suportado em JPEG — gravado com fundo branco")
    fig.savefig(caminho, dpi=150, transparent=transparente)


def _marcas_de_dia(ledger, xs, por_dia: bool):
    marcas = []
    for i, p in enumerate(ledger):
        if i == 0 or ledger[i - 1]["dia"] != p["dia"]:
            marcas.append((xs[i], f"Dia {p['dia'] + 1}"))
    return marcas


def _desenhar_separadores(ax, marcas, por_dia: bool):
    if por_dia:
        return
    for x, rotulo in marcas:
        ax.axvline(x, color="#999999", linewidth=0.7, linestyle=":")
        ax.annotate(rotulo, (x, 1.0), xytext=(3, -12),
                    textcoords="offset points", fontsize=7, color="#555555")


def _marcar_eventos(ax, snapshot, dia, por_dia: bool):
    eventos = [e for e in snapshot.get("log", [])
               if dia is None or e.get("dia") == dia]
    for evento in eventos:
        cor = CORES_EVENTO.get(evento.get("tipo"))
        if not cor:
            continue
        x = (evento["hora"] if por_dia else evento["dia"] * 24 + evento["hora"])
        ax.axvline(x, color=cor, linestyle="--", linewidth=0.9, alpha=0.85)
    return eventos


def _legenda_eventos(ax, eventos):
    tipos = sorted({e["tipo"] for e in eventos if e.get("tipo") in CORES_EVENTO})
    rotulos = {"afundamento": "Afundamento", "nuvem": "Ajuste de nuvens",
               "virada_dia": "Virada de dia", "tarifa": "Troca de tarifa"}
    if tipos:
        handles = [Line2D([], [], color=CORES_EVENTO[t], linestyle="--",
                          linewidth=1.0, label=rotulos.get(t, t))
                   for t in tipos]
        ax.legend(handles=handles, fontsize=6, loc="upper left")


def _filtrar_ledger(snapshot, dias):
    # ''dias'' é UM dia (int|None) ou uma coleção. None = todos os dias.
    if dias is None:
        return list(snapshot["ledger"])
    if isinstance(dias, int):
        return [p for p in snapshot["ledger"] if p["dia"] == dias]
    return [p for p in snapshot["ledger"] if p["dia"] in dias]


def _graf_cargas_barras(fig, snapshot, dias, espessura, fundo, por_dia):
    ax = fig.add_subplot(1, 1, 1)
    dias_sel = ([dias] if dias is not None
                else sorted({p["dia"] for p in snapshot["ledger"]}))
    for dia_c in dias_sel:
        cargas = snapshot.get("cargas_por_barra", {}).get(dia_c, {})
        xs = list(range(24)) if por_dia else [
            p["passo"] for p in snapshot["ledger"] if p["dia"] == dia_c]
        for nome_barra in sorted(cargas):
            ax.plot(xs if por_dia else xs[:len(cargas[nome_barra])],
                    cargas[nome_barra], linewidth=espessura, label=nome_barra)
    ax.set_title("Curvas de carga por barra (kW)", fontsize=10)
    ax.set_xlabel("Hora do dia (h)" if por_dia else "Tempo (h simuladas)")
    ax.set_ylabel("kW")
    if por_dia:
        ax.set_xticks(range(0, 24, 2))
    else:
        ledger = _filtrar_ledger(snapshot, dias_sel)
        _desenhar_separadores(
            ax, _marcas_de_dia(ledger, [p["passo"] for p in ledger], False),
            False)
    if dias_sel:
        ax.legend(fontsize=6, ncol=2)
    return ax


def _graf_geracao_pv(fig, snapshot, dias, espessura, fundo, por_dia):
    ax = fig.add_subplot(1, 1, 1)
    pmpp = snapshot.get("pv_kw_nominal") or (
        snapshot.get("meta", {}).get("pv_kw_nominal") or {})
    ledger = _filtrar_ledger(snapshot, dias)
    xs = [(p["hora"] if por_dia else p["passo"]) for p in ledger]
    nomes = sorted({n for p in ledger for n in p["pv_mult_por_unidade"]})
    for nome in nomes:
        ys = [p["pv_mult_por_unidade"].get(nome, 1.0) * pmpp.get(nome, 0.0)
              for p in ledger]
        ax.plot(xs, ys, linewidth=espessura, label=nome,
                marker="o", markersize=2.5)
    ax.set_title("Geração fotovoltaica (kW)", fontsize=10)
    ax.set_xlabel("Hora do dia (h)" if por_dia else "Tempo (h simuladas)")
    ax.set_ylabel("kW")
    ax.axhline(0, color="#333333", linewidth=0.7)
    if nomes:
        ax.legend(fontsize=6)
    _marcas = _marcas_de_dia(ledger, xs, por_dia)
    if not por_dia:
        _desenhar_separadores(ax, _marcas, False)
    _marcar_eventos(ax, snapshot, None, por_dia)
    return ax


def _graf_bess_soc(fig, snapshot, dias, espessura, fundo, por_dia):
    ax = fig.add_subplot(1, 1, 1)
    ledger = _filtrar_ledger(snapshot, dias)
    xs = [(p["hora"] if por_dia else p["passo"]) for p in ledger]
    nomes = sorted({n for p in ledger for n in p["soc_por_bess"]})
    for nome in nomes:
        ys = [p["soc_por_bess"].get(nome) * 100.0 for p in ledger]
        ax.plot(xs, ys, linewidth=espessura, label=nome,
                marker="o", markersize=2.5)
    ax.set_title("BESS — nível de carga (SoC %)", fontsize=10)
    ax.set_xlabel("Hora do dia (h)" if por_dia else "Tempo (h simuladas)")
    ax.set_ylabel("SoC (%)")
    ax.set_ylim(-5, 105)
    ax.axhline(20, color="#666666", linestyle=":", linewidth=0.8, alpha=0.7)
    ax.axhline(95, color="#666666", linestyle=":", linewidth=0.8, alpha=0.7)
    if nomes:
        ax.legend(fontsize=6)
    if not por_dia:
        _desenhar_separadores(ax, _marcas_de_dia(ledger, xs, por_dia), False)
    return ax


def _graf_bess_potencia(fig, snapshot, dias, espessura, fundo, por_dia):
    ax = fig.add_subplot(1, 1, 1)
    ledger = _filtrar_ledger(snapshot, dias)
    xs = [(p["hora"] if por_dia else p["passo"]) for p in ledger]
    nomes = sorted({n for p in ledger for n in p["kw_por_bess"]})
    for nome in nomes:
        ys = [p["kw_por_bess"].get(nome, 0.0) for p in ledger]
        ax.plot(xs, ys, linewidth=espessura, label=nome,
                marker="o", markersize=2.5)
    ax.set_title("BESS — potência despachada (+descarga / −carga)", fontsize=10)
    ax.set_xlabel("Hora do dia (h)" if por_dia else "Tempo (h simuladas)")
    ax.set_ylabel("kW")
    ax.axhline(0, color="#333333", linewidth=0.8)
    if nomes:
        ax.legend(fontsize=6)
    if not por_dia:
        _desenhar_separadores(ax, _marcas_de_dia(ledger, xs, por_dia), False)
    _marcar_eventos(ax, snapshot, None, por_dia)
    return ax


def _graf_bess_controlador(fig, snapshot, dias, espessura, fundo, por_dia):
    ax = fig.add_subplot(1, 1, 1)
    ledger = _filtrar_ledger(snapshot, dias)
    xs = [(p["hora"] if por_dia else p["passo"]) for p in ledger]
    nomes = sorted({n for p in ledger for n in p["estado_por_bess"]})
    for nome in nomes:
        ys = [NIVEL_ESTADO.get(p["estado_por_bess"].get(nome, "repouso"), 0)
              for p in ledger]
        ax.fill_between(xs, ys, step="mid", alpha=0.45)
        ax.plot(xs, ys, drawstyle="steps-mid", linewidth=espessura, label=nome)
    ax.set_yticks([0, 1, 2])
    ax.set_yticklabels(ROTULOS_ESTADO)
    ax.set_ylim(-0.2, 2.4)
    ax.set_title("BESS — atuação do controlador (com eventos)", fontsize=10)
    ax.set_xlabel("Hora do dia (h)" if por_dia else "Tempo (h simuladas)")
    eventos = _marcar_eventos(ax, snapshot, None, por_dia)
    _legenda_eventos(ax, eventos)
    if nomes:
        ax.legend(fontsize=6, loc="upper right")
    if not por_dia:
        _desenhar_separadores(ax, _marcas_de_dia(ledger, xs, por_dia), False)
    return ax


def _graf_economia(fig, snapshot, dias, espessura, fundo, por_dia):
    ax = fig.add_subplot(1, 1, 1)
    ledger = _filtrar_ledger(snapshot, dias)
    xs = [(p["hora"] if por_dia else p["passo"]) for p in ledger]
    ys = [p["economia_total"] for p in ledger]
    ax.plot(xs, ys, linewidth=espessura, color="#1b8f3a")
    ax.fill_between(xs, ys, alpha=0.25, color="#1b8f3a")
    total = ys[-1] if ys else 0.0
    ax.set_title(f"Economia acumulada (arbitragem) — total R$ {total:,.2f}",
                 fontsize=10)
    ax.set_xlabel("Hora do dia (h)" if por_dia else "Tempo (h simuladas)")
    ax.set_ylabel("R$")
    ax.axhline(0, color="#333333", linewidth=0.8)
    if not por_dia:
        _desenhar_separadores(ax, _marcas_de_dia(ledger, xs, por_dia), False)
    return ax


def _graf_tensao(fig, snapshot, dias, espessura, fundo, por_dia):
    ax = fig.add_subplot(1, 1, 1)
    ledger = _filtrar_ledger(snapshot, dias)
    xs = [(p["hora"] if por_dia else p["passo"]) for p in ledger]
    ax.plot(xs, [p["vmax"] for p in ledger], linewidth=espessura,
            color="#004587", label="Vmax")
    ax.plot(xs, [p["vmin"] for p in ledger], linewidth=espessura,
            color="#c62828", label="Vmin")
    ax.set_title("Tensão — Vmin/Vmax (pu)", fontsize=10)
    ax.set_xlabel("Hora do dia (h)" if por_dia else "Tempo (h simuladas)")
    ax.set_ylabel("pu")
    ax.axhline(0.90, color="#c62828", linestyle="--", linewidth=0.8, alpha=0.7)
    ax.axhline(1.05, color="#666666", linestyle="--", linewidth=0.8, alpha=0.7)
    ax.legend(fontsize=6, loc="lower right")
    if not por_dia:
        _desenhar_separadores(ax, _marcas_de_dia(ledger, xs, por_dia), False)
    return ax


def _graf_fonte_perdas(fig, snapshot, dias, espessura, fundo, por_dia):
    ax = fig.add_subplot(1, 1, 1)
    ledger = _filtrar_ledger(snapshot, dias)
    xs = [(p["hora"] if por_dia else p["passo"]) for p in ledger]
    ax.plot(xs, [p["kw_fonte_bruto"] for p in ledger], linewidth=espessura,
            color="#004587", label="Fonte (bruto)")
    ax.set_xlabel("Hora do dia (h)" if por_dia else "Tempo (h simuladas)")
    ax.set_ylabel("kW (fonte)")
    ax2 = ax.twinx()
    ax2.plot(xs, [p["perdas_kw"] for p in ledger if p["perdas_kw"] is not None],
             linewidth=espessura * 0.8, color="#b35c00", label="Perdas")
    ax2.set_ylabel("kW (perdas)", color="#b35c00")
    ax.set_title("Fonte e perdas (kW)", fontsize=10)
    ax.axhline(0, color="#333333", linewidth=0.8)
    if not por_dia:
        _desenhar_separadores(ax, _marcas_de_dia(ledger, xs, por_dia), False)
    return [ax, ax2]


CONSTRUTORES = {
    "cargas_barras": _graf_cargas_barras,
    "geracao_pv": _graf_geracao_pv,
    "bess_soc": _graf_bess_soc,
    "bess_potencia": _graf_bess_potencia,
    "bess_controlador": _graf_bess_controlador,
    "economia": _graf_economia,
    "tensao": _graf_tensao,
    "fonte_perdas": _graf_fonte_perdas,
}


def exportar_graficos(snapshot: Dict[str, Any], config: Dict[str, Any]) -> Tuple[List[str], List[str]]:
    """Renderiza e grava os gráficos selecionados.

    Parâmetros de config: 'graficos' (chaves de CHAVES_GRAFICOS),
    'dias' (ints 0-based), 'espessura' (float), 'fundo'
    ('branco'|'transparente'|'escuro'), 'formato' ('png'|'jpeg'|'svg'),
    'por_dia' (bool), 'pasta' (str), 'prefixo' (str).
    Devolve (caminhos gravados, avisos).
    """
    chaves = list(config.get("graficos") or [])
    dias = list(config.get("dias") or [])
    if not chaves:
        raise ValueError("Nenhum gráfico selecionado para exportar.")
    if not dias:
        raise ValueError("Nenhum dia selecionado para exportar.")
    for chave in chaves:
        if chave not in CONSTRUTORES:
            raise ValueError(f"Gráfico desconhecido: {chave!r}")

    espessura = float(config.get("espessura", 1.4) or 1.4)
    fundo = str(config.get("fundo", "branco"))
    formato = str(config.get("formato", "png")).lower()
    if formato not in ("png", "jpeg", "svg"):
        raise ValueError(f"Formato não suportado: {formato!r}")
    por_dia = bool(config.get("por_dia", False))
    pasta = str(config.get("pasta") or ".")
    prefixo = str(config.get("prefixo") or "ao_vivo")
    os.makedirs(pasta, exist_ok=True)

    caminhos: List[str] = []
    avisos: List[str] = []
    for chave in chaves:
        construtor = CONSTRUTORES[chave]
        alvos = dias if por_dia else [None]
        for dia in alvos:
            fig = Figure(figsize=(8.0, 4.5), layout="constrained")
            FigureCanvasAgg(fig)
            if fundo == "escuro":
                fig.patch.set_facecolor("#1e1e1e")
            retorno = construtor(fig, snapshot, dia, espessura, fundo, por_dia)
            eixos = retorno if isinstance(retorno, list) else [retorno]
            _finalizar(fig, eixos, fundo)
            sufixo = (f"_Dia{dia + 1}" if por_dia and dia is not None else "")
            caminho = os.path.join(
                pasta, f"{prefixo}_{chave}{sufixo}.{formato}")
            _gravar(fig, caminho, fundo, formato, avisos)
            caminhos.append(caminho)
    return caminhos, avisos
