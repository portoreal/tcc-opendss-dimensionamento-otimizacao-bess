__author__ = 'Pedro Henrique Sousa Pinheiro'
"""Memorial de cálculo da análise de economia de energia — a arbitragem
tarifária entre ponta e fora ponta com o BESS.

O documento traz, hora a hora, o estado comandado ao BESS, o SoC resultante
e a classificação do fluxo: se o sistema compra da rede ou exporta para ela.
Com essas três colunas lado a lado, dá para auditar o comportamento do
equipamento sem reabrir o modelo, e o superdimensionamento aparece na cara:
BESS que exporta é BESS maior que a carga local.
"""

from typing import Dict, Any


LARGURA_LINHA = 110


def _linha_separadora(caractere="-") -> str:
    return caractere * LARGURA_LINHA


def gerar_memorial_economia(resultado: Dict[str, Any]) -> str:
    linhas = []
    tarifa = resultado["tarifa"]

    linhas.append(_linha_separadora("#"))
    linhas.append("MEMORIAL DE CÁLCULO — Economia de Energia (Arbitragem Tarifária BESS)")
    linhas.append(_linha_separadora("#"))
    linhas.append("")
    linhas.append(f"Tarifa utilizada: {tarifa.nome} (subgrupo {tarifa.subgrupo}, modalidade {tarifa.modalidade})")
    linhas.append(f"    - Energia ponta:      R$ {tarifa.tarifa_ponta_kwh:.5f} / kWh")
    linhas.append(f"    - Energia fora ponta: R$ {tarifa.tarifa_fora_ponta_kwh:.5f} / kWh")
    linhas.append(
        f"Horário de ponta considerado: {resultado['horario_ponta_inicio']:02d}h "
        f"às {resultado['horario_ponta_fim']:02d}h")
    linhas.append(f"Dias equivalentes por mês (extrapolação): {resultado['dias_equivalentes_mes']}")
    linhas.append("")

    if resultado.get("alerta_superdimensionamento"):
        # O alerta existe porque o modelo não monetiza energia exportada.
        # Sem esse texto, um resultado econômico nulo seria lido como
        # "BESS inútil", quando na verdade é "BESS grande demais para esta
        # análise".
        linhas.append(_linha_separadora("!"))
        linhas.append("⚠ ALERTA DE ENGENHARIA: SUPERDIMENSIONAMENTO DETECTADO")
        linhas.append(_linha_separadora("!"))
        linhas.append(
            "O BESS analisado apresentou EXPORTAÇÃO de energia para a rede em "
            "pelo menos uma hora do dia representativo (ver coluna 'Fluxo' na "
            "tabela abaixo). Isso ocorre quando a potência de descarga do BESS "
            "excede a carga total do sistema, fazendo o excedente refluir para "
            "a fonte/subestação.")
        linhas.append(
            "Este modelo simplificado de arbitragem tarifária NÃO monetiza "
            "energia exportada (não modela crédito de energia / compensação, "
            "tema regulatório específico e fora do escopo deste módulo). "
            "Portanto, um BESS superdimensionado para a carga local tende a "
            "apresentar resultado econômico NULO ou NEGATIVO nesta análise, "
            "mesmo sendo tecnicamente eficaz para outros fins (ex.: mitigação "
            "de afundamento de tensão, que exige maior potência).")
        linhas.append(
            f"Total exportado no dia representativo: "
            f"{resultado['total_exportado_kwh_bess']:.2f} kWh "
            f"(ponta: {resultado['exportada_ponta_kwh_bess']:.2f} kWh, "
            f"fora ponta: {resultado['exportada_fora_ponta_kwh_bess']:.2f} kWh)")
        linhas.append(
            "RECOMENDAÇÃO: para a análise de ECONOMIA DE ENERGIA, considere "
            "avaliar um BESS com potência (kW) mais próxima da carga total "
            "do sistema, em vez de reaproveitar diretamente a alocação "
            "vencedora do estudo de mitigação de afundamento de tensão "
            "(que tende a favorecer unidades de maior potência).")
        linhas.append("")

    linhas.append(_linha_separadora("="))
    linhas.append("PERFIL HORÁRIO — Potência, Estado do BESS, SoC e Fluxo")
    linhas.append(_linha_separadora("="))
    linhas.append(
        f"{'Hora':<6}{'Período':<12}{'SEM BESS':>12}{'COM BESS':>12}"
        f"{'Estado BESS':>14}{'SoC (%)':>10}{'Fluxo':>16}")
    linhas.append(_linha_separadora())

    perfil_base = {p["hora"]: p for p in resultado["perfil_base"]}
    perfil_bess = {p["hora"]: p for p in resultado["perfil_bess"]}

    for hora in range(24):
        pb = perfil_base.get(hora, {})
        pc = perfil_bess.get(hora, {})
        periodo = "PONTA" if pb.get("ponta") else "fora ponta"

        # Uma linha por hora, com um único BESS por vez. Se o projeto tiver
        # mais de um, a tabela mostra o primeiro em ordem de dicionário e o
        # restante continua disponível nos dados, apenas fora do memorial.
        estados = pc.get("estados_aplicados", {})
        socs = pc.get("soc_depois", {})
        primeiro_nome = next(iter(estados), None)

        estado_texto = estados.get(primeiro_nome, {}).get("estado", "-") if primeiro_nome else "-"
        soc_texto = f"{socs.get(primeiro_nome, 0) * 100:.1f}" if primeiro_nome else "-"

        # Fluxo exportado é sinal de que a descarga do BESS passou da carga
        # do sistema naquela hora.
        exportando = pc.get("kw_exportada", 0) > 0
        fluxo_texto = f"EXPORTANDO {pc.get('kw_exportada', 0):.1f}kW" if exportando else "importando"

        linhas.append(
            f"{hora:02d}h{'':<3}{periodo:<12}{pb.get('kw_comprada', 0):>12.2f}"
            f"{pc.get('kw_comprada', 0):>12.2f}{estado_texto:>14}{soc_texto:>10}"
            f"{fluxo_texto:>16}")

    linhas.append("")
    linhas.append(
        "NOTA DE AUDITORIA: o SoC deve SUBIR durante 'charging' e DESCER "
        "durante 'discharging'. A coluna 'Fluxo' indica 'EXPORTANDO' quando "
        "o BESS injeta mais potência do que a carga local consome (energia "
        "não monetizada neste modelo - ver alerta acima, se presente).")
    linhas.append("")

    linhas.append(_linha_separadora("="))
    linhas.append("RESUMO DE ENERGIA E CUSTO (apenas energia efetivamente COMPRADA)")
    linhas.append(_linha_separadora("="))
    linhas.append(
        f"Energia em ponta       — SEM BESS: {resultado['energia_ponta_kwh_base']:.2f} kWh"
        f"   |   COM BESS: {resultado['energia_ponta_kwh_bess']:.2f} kWh")
    linhas.append(
        f"Energia fora de ponta  — SEM BESS: {resultado['energia_fora_ponta_kwh_base']:.2f} kWh"
        f"   |   COM BESS: {resultado['energia_fora_ponta_kwh_bess']:.2f} kWh")
    linhas.append("")
    linhas.append(f"Custo diário SEM BESS: R$ {resultado['custo_diario_base']:.2f}")
    linhas.append(f"Custo diário COM BESS: R$ {resultado['custo_diario_bess']:.2f}")
    linhas.append(f"Economia diária:       R$ {resultado['economia_diaria']:.2f}")
    linhas.append(f"Economia mensal (estimada): R$ {resultado['economia_mensal']:.2f}")
    linhas.append(f"Economia anual (estimada):  R$ {resultado['economia_anual']:.2f}")
    linhas.append("")

    if resultado.get("reducao_demanda_ponta_kw", 0) > 0:
        linhas.append("Estimativa adicional (simplificada) de redução de demanda de ponta:")
        linhas.append(
            f"    Demanda máxima em ponta — SEM BESS: {resultado['demanda_ponta_kw_base']:.2f} kW"
            f"   |   COM BESS: {resultado['demanda_ponta_kw_bess']:.2f} kW")
        linhas.append(f"    Redução: {resultado['reducao_demanda_ponta_kw']:.2f} kW")
        linhas.append(
            f"    Economia mensal estimada em demanda: "
            f"R$ {resultado['economia_demanda_mensal_estimada']:.2f}")
        linhas.append("")

    # Payback depende de custo informado e de economia positiva. Sem os dois,
    # o memorial diz por que não calculou, em vez de imprimir um número
    # enganoso.
    if resultado.get("custo_bess_brl"):
        linhas.append(f"Custo do BESS considerado: R$ {resultado['custo_bess_brl']:,.2f}")
        if resultado.get("payback_anos") is not None:
            linhas.append(f"Payback simples (energia): {resultado['payback_anos']:.2f} ano(s)")
        else:
            linhas.append(
                "Payback simples: não calculado (economia anual estimada "
                "é zero ou negativa).")
    else:
        linhas.append("Custo do BESS não informado - payback não calculado.")

    linhas.append("")
    return "\n".join(linhas)


def salvar_memorial_economia(texto: str, caminho_arquivo: str) -> None:
    # O texto é montado como string e só aqui vai para o disco, o que permite
    # mostrar o memorial na tela antes de qualquer gravação.
    with open(caminho_arquivo, "w", encoding="utf-8") as f:
        f.write(texto)