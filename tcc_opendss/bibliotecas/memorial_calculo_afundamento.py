__author__ = 'Pedro Henrique Sousa Pinheiro'
"""Gerador de memorial de cálculo para o Estudo de Afundamento de Tensão
(voltage sag) usado na Otimização de Alocação de BESS.

Este módulo é puramente de RELATÓRIO/TRANSPARÊNCIA: ele NÃO refaz nenhum
cálculo elétrico por conta própria. Todos os valores de tensão em pu
utilizados aqui são exatamente os mesmos já calculados pelo motor
OpenDSS dentro de estudo_afundamento.rodar_estudo() (fluxo de potência
trifásico desequilibrado completo, não uma fórmula simplificada).

O objetivo deste memorial é permitir que o usuário AUDITE, barra a barra
e cenário a cenário, por que cada barra foi (ou não foi) classificada
como estando em afundamento de tensão, evitando que um resultado como
"0 barras em afundamento" pareça uma "caixa preta" ou um possível bug -
quando, na verdade, pode ser um resultado fisicamente correto para
redes eletricamente "rígidas" (fonte forte / linhas curtas).

METODOLOGIA (já documentada em estudo_afundamento.py, repetida aqui por
completude do memorial):
    - Referência: "área de vulnerabilidade" (Bollen, 2000).
    - Critério de amplitude (ANEEL): afundamento = 0,10 <= V < 0,90 pu.
    - V < 0,10 pu: classificado como possível INTERRUPÇÃO (fora do
      escopo de "afundamento"), não contabilizado como sag.
    - V >= 0,90 pu: considerado dentro da faixa normal de operação.
    - Duração: não avaliada por este motor (OpenDSS é quase-estático);
      assume-se que o defeito está dentro da janela "momentânea" da
      ANEEL (1 ciclo a 3 s). Ver limitação documentada em
      estudo_afundamento.py.
"""

from typing import Dict, Any, List, Optional


LARGURA_LINHA = 78


def _linha_separadora(caractere="-") -> str:
    return caractere * LARGURA_LINHA


def _classificar_valor(valor: float, limite_inferior: float, limite_superior: float) -> str:
    """Classifica um único valor de tensão (pu) segundo os limiares do
    estudo. Usado para dar transparência total sobre CADA valor, e não
    apenas o resultado binário "em sag / não em sag"."""
    if valor < limite_inferior:
        return "ABAIXO DO LIMITE (possível interrupção, fora do critério de sag)"
    if valor < limite_superior:
        return "EM AFUNDAMENTO (sag)"
    return "Normal (dentro da faixa aceitável)"


def _resumir_barra(valores: List[float]) -> Optional[Dict[str, float]]:
    if not valores:
        return None
    return {"minimo": min(valores), "maximo": max(valores)}


def _nome_base_barra(bus: str) -> str:
    """Remove eventuais sufixos de nó (ex.: 'barra1.1' -> 'barra1'),
    usado para comparar com o nome da barra em falta (que é informado
    sem sufixo de nó pelo restante do código)."""
    return bus.split(".")[0].lower()


def _gerar_secao_cenario(indice: int, cenario: Dict[str, Any],
                          limite_inferior: float, limite_superior: float) -> str:
    linhas = []
    bus_falta = cenario["bus_falta"]
    tipo_falta = cenario["tipo_falta"]
    pu_por_barra = cenario.get("pu", {})
    nome_faltoso = _nome_base_barra(bus_falta)

    linhas.append(_linha_separadora("="))
    linhas.append(f"CENÁRIO {indice}: Falta em '{bus_falta}' — tipo: {tipo_falta}")
    linhas.append(_linha_separadora("="))

    # CORREÇÃO 2026-10-30 (semântica de colapso): resultados novos
    # trazem 'convergiu'=False no cenário divergente, com SENTINEL
    # limite_inferior em 'pu'. O memorial exibe o aviso e a tabela de
    # sentinels (auditoria fiel à semântica: janela completa em todas
    # as barras monitoradas).
    convergiu = cenario.get("convergiu", True)
    if not convergiu:
        linhas.append(
            "⚠ A solução NÃO CONVERGIU (tratado como colapso) para este "
            "cenário. Cada barra monitorada (exceto a barra em falta) "
            "recebeu o SENTINEL de tensão = "
            f"{limite_inferior:.2f} pu — estes NÃO são valores medidos: "
            "todas as barras ficam classificadas em afundamento e a "
            "profundidade do cenário é a janela completa, penalizando a "
            "severidade do candidato (divergência sob falta + injeção é "
            "colapso de tensão não demonstravelmente mitigável).")
        linhas.append("")
    elif not pu_por_barra:
        # Resultado gerado antes do campo 'convergiu' existir: sem
        # medição, o aviso só pode ser genérico.
        linhas.append(
            "⚠ A solução NÃO CONVERGIU para este cenário. Por critério "
            "conservador de engenharia, todas as barras monitoradas "
            "(exceto a barra em falta) foram consideradas em afundamento "
            "neste cenário (não convergência sob falta severa é, por si "
            "só, indicativo de colapso de tensão local).")
        linhas.append("")
        return "\n".join(linhas)

    linhas.append(f"{'Barra':<20}{'V_min (pu)':>14}{'V_max (pu)':>14}   Classificação")
    linhas.append(_linha_separadora())

    barras_em_sag_neste_cenario = []

    for bus in sorted(pu_por_barra.keys()):
        if _nome_base_barra(bus) == nome_faltoso:
            linhas.append(f"{bus:<20}{'--':>14}{'--':>14}   (barra em falta, excluída da análise)")
            continue

        resumo = _resumir_barra(pu_por_barra[bus])
        if resumo is None:
            linhas.append(f"{bus:<20}{'--':>14}{'--':>14}   (sem nó energizado detectado)")
            continue

        classificacao = _classificar_valor(resumo["minimo"], limite_inferior, limite_superior)
        if "AFUNDAMENTO" in classificacao:
            barras_em_sag_neste_cenario.append(bus)

        linhas.append(
            f"{bus:<20}{resumo['minimo']:>14.4f}{resumo['maximo']:>14.4f}   {classificacao}")

    linhas.append(_linha_separadora())
    if barras_em_sag_neste_cenario:
        linhas.append(
            f"Barras classificadas em AFUNDAMENTO neste cenário: "
            f"{', '.join(barras_em_sag_neste_cenario)}")
    else:
        linhas.append(
            "Nenhuma barra classificada em afundamento neste cenário "
            f"(todas as barras monitoradas permaneceram >= {limite_superior:.2f} pu, "
            f"ou a única que caiu abaixo de {limite_inferior:.2f} pu foi a própria "
            "barra em falta).")
    linhas.append("")

    return "\n".join(linhas)


def gerar_memorial_estudo(
    resultado_estudo: Dict[str, Any],
    limite_inferior: float = 0.1,
    limite_superior: float = 0.9,
    r_falta_solida: float = 0.0001,
    r_falta_alta_impedancia: float = 40.0,
    titulo: str = "Estudo de Afundamento de Tensão",
) -> str:
    """Gera o texto completo do memorial de cálculo para UM resultado de
    estudo (a saída de estudo_afundamento.rodar_estudo()).

    Este memorial mostra, cenário a cenário e barra a barra, o valor de
    tensão mínimo/máximo em pu encontrado e sua classificação, permitindo
    auditar exatamente por que o resultado agregado (barras_em_sag_geral)
    chegou ao valor apresentado — incluindo o caso de resultado "0
    barras em afundamento", que pode ser fisicamente correto para redes
    eletricamente rígidas (fonte forte e/ou linhas curtas)."""

    linhas = []
    linhas.append(_linha_separadora("#"))
    linhas.append(f"MEMORIAL DE CÁLCULO — {titulo}")
    linhas.append(_linha_separadora("#"))
    linhas.append("")
    linhas.append("Metodologia: Área de vulnerabilidade (Bollen, 2000).")
    linhas.append("Critério de classificação de afundamento (ANEEL):")
    linhas.append(f"    - Interrupção (fora do escopo): V < {limite_inferior:.2f} pu")
    linhas.append(f"    - AFUNDAMENTO (sag):            {limite_inferior:.2f} <= V < {limite_superior:.2f} pu")
    linhas.append(f"    - Normal:                        V >= {limite_superior:.2f} pu")
    linhas.append("")
    linhas.append("Parâmetros de impedância de falta utilizados:")
    linhas.append(f"    - Falta sólida (trifásica / monofásica com terra): r = {r_falta_solida} ohm")
    linhas.append(f"    - Falta de alta impedância (monofásica sem terra efetiva): r = {r_falta_alta_impedancia} ohm")
    linhas.append("")
    linhas.append(
        "LIMITAÇÃO METODOLÓGICA: o OpenDSS resolve o sistema em regime "
        "fasorial quase-estático. A duração real do afundamento depende "
        "do tempo de atuação da proteção (estudo de coordenação "
        "separado). Assume-se que o defeito está dentro da janela "
        "'momentânea' da ANEEL (1 ciclo a 3 s). A classificação aqui "
        "concentra-se exclusivamente no critério de AMPLITUDE.")
    linhas.append("")

    bess_list = resultado_estudo.get("bess_list", [])
    if bess_list:
        linhas.append(f"Configuração de BESS considerada neste estudo ({len(bess_list)} unidade(s)):")
        for i, bess in enumerate(bess_list, start=1):
            linhas.append(
                f"    {i}. Barra: {bess.get('bus')} | "
                f"kW: {bess.get('kw')} | kWh: {bess.get('kwh')}")
    else:
        linhas.append("Configuração de BESS considerada neste estudo: NENHUMA (caso base).")
    linhas.append("")

    detalhe_por_falta = resultado_estudo.get("detalhe_por_falta", [])
    for i, cenario in enumerate(detalhe_por_falta, start=1):
        linhas.append(_gerar_secao_cenario(i, cenario, limite_inferior, limite_superior))

    barras_em_sag_geral = sorted(resultado_estudo.get("barras_em_sag_geral", []))
    linhas.append(_linha_separadora("#"))
    linhas.append("RESUMO GERAL DO ESTUDO")
    linhas.append(_linha_separadora("#"))
    linhas.append(f"Total de cenários simulados (barras x tipos de falta): {len(detalhe_por_falta)}")
    if barras_em_sag_geral:
        linhas.append(
            f"Barras que apresentaram afundamento em PELO MENOS UM cenário "
            f"({len(barras_em_sag_geral)}): {', '.join(barras_em_sag_geral)}")
    else:
        linhas.append(
            "NENHUMA barra apresentou afundamento em nenhum dos cenários "
            "simulados. Consulte as tabelas por cenário acima para "
            "verificar os valores de tensão mínima (V_min) efetivamente "
            "encontrados em cada barra — este resultado é fisicamente "
            "esperado em redes eletricamente rígidas (fonte com alta "
            "potência de curto-circuito e/ou linhas curtas entre as "
            "barras).")
    linhas.append("")

    return "\n".join(linhas)


def gerar_memorial_comparativo(
    resultado_base: Dict[str, Any],
    resultado_otimizado: Dict[str, Any],
    limite_inferior: float = 0.1,
    limite_superior: float = 0.9,
    r_falta_solida: float = 0.0001,
    r_falta_alta_impedancia: float = 40.0,
) -> str:
    """Gera um memorial ÚNICO comparando o caso base (sem BESS) com o
    caso otimizado (com a alocação de BESS selecionada pelo MILP),
    incluindo os dois memoriais individuais em sequência e uma seção de
    comparação direta ao final."""

    partes = []

    partes.append(gerar_memorial_estudo(
        resultado_base, limite_inferior, limite_superior,
        r_falta_solida, r_falta_alta_impedancia,
        titulo="Caso Base (SEM BESS)"))

    partes.append(gerar_memorial_estudo(
        resultado_otimizado, limite_inferior, limite_superior,
        r_falta_solida, r_falta_alta_impedancia,
        titulo="Caso Otimizado (COM alocação de BESS)"))

    barras_base = set(resultado_base.get("barras_em_sag_geral", []))
    barras_otim = set(resultado_otimizado.get("barras_em_sag_geral", []))
    barras_resolvidas = barras_base - barras_otim
    barras_novas = barras_otim - barras_base

    partes.append(_linha_separadora("#"))
    partes.append("COMPARAÇÃO FINAL: CASO BASE x CASO OTIMIZADO")
    partes.append(_linha_separadora("#"))
    partes.append(f"Barras em afundamento — caso base:       {len(barras_base)}")
    partes.append(f"Barras em afundamento — caso otimizado:  {len(barras_otim)}")
    partes.append(f"Redução líquida: {len(barras_base) - len(barras_otim)} barra(s)")
    partes.append("")

    if barras_resolvidas:
        partes.append(
            f"Barras que DEIXARAM de apresentar afundamento com o BESS "
            f"alocado ({len(barras_resolvidas)}): {', '.join(sorted(barras_resolvidas))}")
    else:
        partes.append(
            "Nenhuma barra deixou de apresentar afundamento com a "
            "alocação de BESS testada.")

    if barras_novas:
        partes.append(
            f"⚠ ATENÇÃO: barras que PASSARAM a apresentar afundamento "
            f"após a alocação do BESS ({len(barras_novas)}): "
            f"{', '.join(sorted(barras_novas))} — verifique possível "
            "interação adversa (ex.: injeção de corrente de falta pelo "
            "inversor alterando a distribuição de tensão).")

    if not barras_base:
        partes.append("")
        partes.append(
            "OBSERVAÇÃO IMPORTANTE: o caso base já não apresentava "
            "nenhuma barra em afundamento antes da alocação do BESS. "
            "Isso explica por que o otimizador MILP não selecionou "
            "nenhuma alocação (não há benefício de mitigação de "
            "afundamento a ser obtido nesta rede/configuração de "
            "faltas). Isso NÃO indica necessariamente um erro no "
            "software — pode ser uma característica real da rede "
            "simulada (ex.: rede pequena, fonte com alta potência de "
            "curto-circuito, linhas curtas). Para validar, tente "
            "aumentar o comprimento das linhas entre a fonte e as "
            "barras candidatas, ou reduzir a potência de curto-circuito "
            "da Fonte (Vsource), e rode o estudo novamente.")

    return "\n".join(partes)


def salvar_memorial(texto: str, caminho_arquivo: str) -> None:
    """Salva o texto do memorial em um arquivo .txt no caminho informado."""
    with open(caminho_arquivo, "w", encoding="utf-8") as f:
        f.write(texto)