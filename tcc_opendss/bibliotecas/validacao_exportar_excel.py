# -*- coding: utf-8 -*-
"""
Exporta os resultados da Validação do Modelo Computacional para planilha
Excel (.xlsx), via openpyxl.

O módulo não depende de GUI. Ele é só apresentação e gravação, o que
mantém separadas a camada de dados (validacao_ieee.py) e a de apresentação
(validacao_ui.py). A convenção vem do formatador_tabela do projeto de
referência "gerenciamento_de_demandas".

Estrutura do arquivo gerado:
  - Aba "Resumo"       : uma linha por sistema, com status colorido,
                         erro máximo, contagem de barras comparadas,
                         exceções documentadas, mensagem e nota do sistema.
  - Aba "Detalhamento" : uma linha por (barra, fase) de cada sistema,
                         com tensões de referência e simulada, mais o erro.
  - Aba "Memorial"     : o memorial de cálculo, linha a linha.

Formato de entrada (contrato de dados):

    resultados: dict {nome_sistema: resultado}, onde 'resultado' possui:
        "status": str  ("APROVADO" | "REPROVADO" | "PENDENTE" | "ERRO")
        "mensagem": str  (pode incluir o sufixo " | NOTA: <texto longo>")
        "erro_maximo_pct": float ou None
        "erro_maximo_com_excecoes_pct": float ou None
        "detalhamento": lista de dicts:
            {"barra": str, "fase": str,
             "tensao_referencia": float | None,
             "tensao_simulada": float | None,
             "erro_pct": float | None,
             "excecao": bool,
             "observacao": str}
        "excecoes_documentadas": dict {barra: texto de justificativa}
        "nota_sistema": str ou None

    memorial_texto: str  (memorial de cálculo completo, texto corrido)
    caminho_destino: str  (caminho do arquivo .xlsx a ser gravado)

NOTAS DE IMPLEMENTAÇÃO
- O azul institucional (#004587) nos cabeçalhos é a identidade visual do
  projeto, coerente com os demais artefatos do TCC.
- O campo "observacao" do detalhamento JÁ pode chegar prefixado com
  "[EXCEÇÃO DOCUMENTADA] " pela camada de comparação (validacao_ieee.py,
  função comparar_resultados). A prefixação aqui é idempotente e só aplica
  quando o marcador ainda não existe; sem isso o texto sairia duplicado.
- As exceções do openpyxl (permissão de arquivo, caminho inválido) são
  deliberadamente NÃO capturadas. Tratar é papel do chamador, na camada de
  UI, que tem contexto para mostrar mensagem adequada ao usuário.
"""

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter


# ============================================================
# Constantes de estilo (identidade visual do projeto)
# ============================================================

COR_CABECALHO = "004587"      # azul institucional — cabeçalhos de todas as abas
COR_FONTE_CABECALHO = "FFFFFF"
COR_ZEBRA = "F4F7FA"          # faixa alternada nas linhas pares

# Cores de fonte por status (fonte colorida e negrita na aba Resumo)
COR_STATUS = {
    "APROVADO": "107C10",     # verde
    "REPROVADO": "C42B1C",    # vermelho
    "PENDENTE": "B25000",     # laranja
    "ERRO": "B25000",         # laranja
}
COR_STATUS_PADRAO = "333333"  # status não reconhecido

LARGURA_MAXIMA_COLUNA = 60
LARGURA_MINIMA_COLUNA = 10


# ============================================================
# Helpers internos de estilo
# ============================================================

def _estilo_cabecalho(celula):
    """Estilo padrão de cabeçalho: fundo azul institucional, fonte branca
    em negrito, alinhamento centralizado na vertical."""
    celula.font = Font(name="Calibri", size=10, bold=True,
                       color=COR_FONTE_CABECALHO)
    celula.fill = PatternFill("solid", fgColor=COR_CABECALHO)
    celula.alignment = Alignment(horizontal="center", vertical="center",
                                 wrap_text=True)


def _cor_status(status):
    """Cor correspondente ao status, em hex sem '#'. Status desconhecido
    cai na cor neutra, o que evita célula sem cor no meio da tabela."""
    if status is None:
        return COR_STATUS_PADRAO
    return COR_STATUS.get(str(status).upper(), COR_STATUS_PADRAO)


def _largura_coluna(valores, largura_minima=LARGURA_MINIMA_COLUNA,
                    largura_maxima=LARGURA_MAXIMA_COLUNA):
    """Largura de coluna ajustada ao conteúdo textual.

    A conta é o comprimento da maior representação textual, mais 2
    caracteres de folga, respeitados os limites mínimo e máximo. Valores
    None ficam fora do cálculo. Em conteúdo multilinha só a primeira linha
    conta, porque é ela que define a largura visível.
    """
    maior = 0
    for valor in valores:
        if valor is None:
            continue
        texto = str(valor)
        # Só a primeira linha conta (conteúdo multilinha).
        primeira_linha = texto.split("\n", 1)[0]
        maior = max(maior, len(primeira_linha))
    largura = maior + 2
    return max(largura_minima, min(largura, largura_maxima))


def _remover_nota_da_mensagem(mensagem):
    """Remove o sufixo ' | NOTA: <texto>' da mensagem, quando presente.

    validar_sistema (validacao_ieee.py) acrescenta esse sufixo para que a
    mensagem agregada carregue a nota. Na planilha a nota tem coluna
    própria, então repeti-la na mensagem seria redundância.
    """
    if not mensagem:
        return mensagem
    if " | NOTA:" in mensagem:
        return mensagem.split(" | NOTA:", 1)[0]
    return mensagem


# ============================================================
# Construção das abas
# ============================================================

def _montar_aba_resumo(wb, resultados):
    """Cria e preenche a aba 'Resumo'."""
    ws = wb.active
    ws.title = "Resumo"

    cabecalhos = [
        "Sistema",
        "Status",
        "Erro máx. (%)",
        "Erro máx. c/ exceções (%)",
        "Barras comparadas",
        "Exceções documentadas",
        "Mensagem",
        "Nota do sistema",
    ]
    ws.append(cabecalhos)

    for indice, nome in enumerate(cabecalhos, start=1):
        _estilo_cabecalho(ws.cell(row=1, column=indice))

    linhas_dados = []
    for nome_sistema, resultado in resultados.items():
        detalhamento = resultado.get("detalhamento") or []
        # Barra comparada é a que tem erro calculado. As demais entram como
        # pendência e não devem inflar a contagem.
        barras_comparadas = sum(
            1 for item in detalhamento if item.get("erro_pct") is not None
        )

        excecoes = resultado.get("excecoes_documentadas") or {}
        texto_excecoes = ", ".join(str(b) for b in excecoes.keys()) if excecoes else "--"

        mensagem = _remover_nota_da_mensagem(resultado.get("mensagem"))
        nota = resultado.get("nota_sistema")

        linhas_dados.append({
            "nome": nome_sistema,
            "status": resultado.get("status"),
            "erro_max": resultado.get("erro_maximo_pct"),
            "erro_max_exc": resultado.get("erro_maximo_com_excecoes_pct"),
            "barras": barras_comparadas,
            "excecoes": texto_excecoes,
            "mensagem": mensagem,
            "nota": nota,
        })

    for i, dados in enumerate(linhas_dados):
        # Linha 1 é o cabeçalho; os dados começam na 2.
        linha = i + 2
        ws.cell(row=linha, column=1, value=dados["nome"])

        cel_status = ws.cell(row=linha, column=2, value=dados["status"])
        cel_status.font = Font(name="Calibri", size=10, bold=True,
                               color=_cor_status(dados["status"]))
        cel_status.alignment = Alignment(horizontal="center", vertical="top")

        cel_erro = ws.cell(row=linha, column=3, value=dados["erro_max"])
        if dados["erro_max"] is not None:
            cel_erro.number_format = "0.0000"

        cel_erro_exc = ws.cell(row=linha, column=4, value=dados["erro_max_exc"])
        if dados["erro_max_exc"] is not None:
            cel_erro_exc.number_format = "0.0000"

        ws.cell(row=linha, column=5, value=dados["barras"])
        ws.cell(row=linha, column=6, value=dados["excecoes"])
        ws.cell(row=linha, column=7, value=dados["mensagem"])

        cel_nota = ws.cell(row=linha, column=8, value=dados["nota"])
        cel_nota.alignment = Alignment(wrap_text=True, vertical="top")

    # Larguras das colunas
    ws.column_dimensions["A"].width = _largura_coluna(
        [d["nome"] for d in linhas_dados], largura_minima=18)
    ws.column_dimensions["B"].width = 14
    ws.column_dimensions["C"].width = 16
    ws.column_dimensions["D"].width = 20
    ws.column_dimensions["E"].width = 16
    ws.column_dimensions["F"].width = 22
    ws.column_dimensions["G"].width = _largura_coluna(
        [d["mensagem"] for d in linhas_dados], largura_minima=30)
    ws.column_dimensions["H"].width = 70

    ws.freeze_panes = "A2"


def _montar_aba_detalhamento(wb, resultados):
    """Cria e preenche a aba 'Detalhamento'."""
    ws = wb.create_sheet(title="Detalhamento")

    cabecalhos = [
        "Sistema",
        "Barra",
        "Fase",
        "Tensão referência (pu)",
        "Tensão simulada (pu)",
        "Erro (%)",
        "Observação",
    ]
    ws.append(cabecalhos)

    for indice in range(1, len(cabecalhos) + 1):
        _estilo_cabecalho(ws.cell(row=1, column=indice))

    linha = 2
    for nome_sistema, resultado in resultados.items():
        detalhamento = resultado.get("detalhamento") or []
        for item in detalhamento:
            observacao = item.get("observacao") or ""
            if item.get("excecao") and not observacao.startswith("[EXCEÇÃO DOCUMENTADA]"):
                observacao = "[EXCEÇÃO DOCUMENTADA] " + observacao

            ws.cell(row=linha, column=1, value=nome_sistema)
            ws.cell(row=linha, column=2, value=item.get("barra"))
            ws.cell(row=linha, column=3, value=item.get("fase"))

            cel_ref = ws.cell(row=linha, column=4,
                              value=item.get("tensao_referencia"))
            if item.get("tensao_referencia") is not None:
                cel_ref.number_format = "0.00000"

            cel_sim = ws.cell(row=linha, column=5,
                              value=item.get("tensao_simulada"))
            if item.get("tensao_simulada") is not None:
                cel_sim.number_format = "0.00000"

            cel_erro = ws.cell(row=linha, column=6, value=item.get("erro_pct"))
            if item.get("erro_pct") is not None:
                cel_erro.number_format = "0.0000"

            ws.cell(row=linha, column=7, value=observacao)

            # Zebra: linhas pares (índice par na planilha, ou seja, a
            # segunda linha de dados, quarta etc.) recebem faixa clara.
            if linha % 2 == 0:
                for coluna in range(1, len(cabecalhos) + 1):
                    ws.cell(row=linha, column=coluna).fill = PatternFill(
                        "solid", fgColor=COR_ZEBRA)

            linha += 1

    ultima_linha = max(linha - 1, 1)
    ws.auto_filter.ref = f"A1:{get_column_letter(len(cabecalhos))}{ultima_linha}"

    # Larguras por conteúdo
    ws.column_dimensions["A"].width = 30
    ws.column_dimensions["B"].width = 12
    ws.column_dimensions["C"].width = 8
    ws.column_dimensions["D"].width = 20
    ws.column_dimensions["E"].width = 20
    ws.column_dimensions["F"].width = 12
    ws.column_dimensions["G"].width = _largura_coluna(
        ["Observação"], largura_minima=40)

    ws.freeze_panes = "A2"


def _montar_aba_memorial(wb, memorial_texto):
    """Cria e preenche a aba 'Memorial' com o texto do memorial, linha a
    linha, na coluna A, em fonte monoespaçada."""
    ws = wb.create_sheet(title="Memorial")

    texto = memorial_texto if memorial_texto else ""
    # Memorial vazio vira uma única célula em branco: a aba existe, mas não
    # fica com zero linhas, o que confundiria a leitura da planilha.
    linhas = texto.split("\n") if texto else [""]

    for i, linha_texto in enumerate(linhas, start=1):
        celula = ws.cell(row=i, column=1, value=linha_texto)
        celula.font = Font(name="Consolas", size=9)

    ws.column_dimensions["A"].width = 120


# ============================================================
# API pública
# ============================================================

def exportar_validacao_excel(resultados: dict, memorial_texto: str,
                             caminho_destino: str) -> None:
    """Exporta os resultados da validação para um arquivo .xlsx.

    Parâmetros:
        resultados      : dict {nome_sistema: resultado} (ver contrato no
                          cabeçalho do módulo).
        memorial_texto  : memorial de cálculo completo (texto corrido).
        caminho_destino : caminho completo do arquivo .xlsx a ser gravado.

    Exceções de openpyxl (ex.: permissão negada, diretório inexistente)
    não são tratadas aqui — são repassadas ao chamador.
    """
    wb = Workbook()

    _montar_aba_resumo(wb, resultados)
    _montar_aba_detalhamento(wb, resultados)
    _montar_aba_memorial(wb, memorial_texto)

    wb.save(caminho_destino)


# ============================================================
# Teste manual mínimo
# ============================================================

if __name__ == "__main__":
    from openpyxl import load_workbook

    resultados_teste = {
        "IEEE 13 Node Test Feeder": {
            "status": "APROVADO",
            "mensagem": "Erro máximo de tensão: 0.1350 % (dentro da tolerância de 0.5 %)",
            "erro_maximo_pct": 0.1350,
            "erro_maximo_com_excecoes_pct": 0.1350,
            "detalhamento": [
                {"barra": "632", "fase": "1", "tensao_referencia": 1.0210,
                 "tensao_simulada": 1.0205, "erro_pct": 0.0489,
                 "excecao": False, "observacao": ""},
                {"barra": "633", "fase": "2", "tensao_referencia": 1.0180,
                 "tensao_simulada": 1.0150, "erro_pct": 0.2947,
                 "excecao": False, "observacao": ""},
            ],
            "excecoes_documentadas": {},
            "nota_sistema": None,
        },
        "IEEE 123 Node Test Feeder (corrigido)": {
            "status": "APROVADO",
            "mensagem": "Erro máximo de tensão: 0.1356 % (dentro da tolerância) | NOTA: "
                        "Arquivo derivado (NÃO oficial), elaborado neste trabalho.",
            "erro_maximo_pct": 0.1356,
            "erro_maximo_com_excecoes_pct": 1.5469,
            "detalhamento": [
                {"barra": "610", "fase": "2", "tensao_referencia": 1.0260,
                 "tensao_simulada": 1.0101, "erro_pct": 1.5469,
                 "excecao": True,
                 "observacao": "[EXCEÇÃO DOCUMENTADA] Secundário Delta-Delta isolado."},
            ],
            "excecoes_documentadas": {
                "610": "Secundário Delta-Delta isolado, sem carga, sem terra."},
            "nota_sistema": "Arquivo derivado com as 3 chaves normalmente abertas.",
        },
    }

    caminho_teste = "teste_export.xlsx"
    exportar_validacao_excel(
        resultados_teste,
        "MEMORIAL DE CÁLCULO\n===================\nLinha de teste do memorial.\n",
        caminho_teste,
    )

    wb_lido = load_workbook(caminho_teste)
    print("Abas:", wb_lido.sheetnames)
    for nome_aba in wb_lido.sheetnames:
        ws = wb_lido[nome_aba]
        print(f"  {nome_aba}: {ws.max_row} linhas x {ws.max_column} colunas")
    print("Teste de exportação OK.")
