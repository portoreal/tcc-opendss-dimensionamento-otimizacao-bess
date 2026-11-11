"""Verificador de marcadores de estilo nos artefatos de escrita do projeto.

Fonte dos critérios: "Diretrizes de estilo de escrita (naturalização /
redução de cara de IA)" — conectivos de IA a usar com moderação, hedging
genérico e fechos de parágrafo de resumo.

Escopo de varredura:
  - tcc_opendss/bibliotecas/*.py  -> SOMENTE comentários (#) e docstrings
  - README.md
  - tcc_opendss/hardware/README.md
  - doc/manual_usuario.html
  - doc/manual_desenvolvedor.html -> texto fora de <style>/<script>
  - LICENSE.md

Uso:
    python doc/verificar_estilo.py

Saída: contagem por arquivo e veredito. Exit code 0 quando APROVADO,
1 quando houver marcador fora das exceções documentadas.

Sem dependências externas (stdlib apenas). Texto lido como UTF-8-sig para
tolerar BOM eventual.
"""

import ast
import io
import os
import re
import sys
import tokenize

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIR_BIBLIOTECAS = os.path.join(RAIZ, "tcc_opendss", "bibliotecas")

# Conectivos e fórmulas listados na diretriz (comparação sem distinção de
# caixa; a busca é por substring, então flexões próximas também casam).
MARCADORES = [
    "Além disso",
    "É importante destacar",
    "É importante ressaltar",
    "Nesse sentido",
    "Vale ressaltar",
    "Em suma",
    "de forma geral",
    "Dessa forma",
    "É fundamental",
    "cabe destacar",
    "Importante destacar",
    "ressalta-se que",
    "Vale lembrar",
    "deve-se notar",
    "Em resumo",
    "Em síntese",
    "se faz necessário",
    "faz-se necessário",
    "pode-se observar",
    "é possível observar que",
]

# Exceções documentadas (não marcadas).
# 1) "é válido" / "NÃO é válido": uso semântico (predicado de validade de
#    um resultado), não conectivo de IA. Não entra na lista porque não é
#    sequer um marcador; registrado aqui como decisão explícita.
# 2) "Portanto" é conectivo listado na diretriz, mas NÃO compõe a lista
#    MARCADORES acima (foi removido do código, não apenas tolerado); em
#    memorial_calculo_economia.py ele aparece em string de relatório
#    gerado, fora do escopo de comentários. Strings não são varridas.
EXCECOES = {
    "semantico": ["é válido", "NÃO é válido"],
    "fora_de_escopo": ["Portanto (string de relatório em memorial_calculo_economia.py)"],
}

HTML_TAGS_IGNORADAS = re.compile(
    r"<(style|script)\b[^>]*>.*?</\1\s*>", re.IGNORECASE | re.DOTALL
)


def ler_texto(caminho):
    with io.open(caminho, "r", encoding="utf-8-sig", errors="replace") as fh:
        return fh.read()


def linhas_com_marcadores(texto, base_linha=1):
    """Retorna [(linha_absoluta, marcador, trecho)] para um bloco de texto."""
    achados = []
    for deslocamento, linha in enumerate(texto.splitlines()):
        minuscula = linha.lower()
        for marcador in MARCADORES:
            if marcador.lower() in minuscula:
                achados.append((base_linha + deslocamento, marcador, linha.strip()))
    return achados


def extrair_texto_py(caminho):
    """Concatena comentários e docstrings do arquivo, preservando a linha.

    Código e strings comuns ficam de fora: só comentários (#), a docstring
    de módulo e as docstrings de funções/classes são avaliados.
    """
    origem = ler_texto(caminho)
    blocos = []
    try:
        for token in tokenize.generate_tokens(io.StringIO(origem).readline):
            if token.type == tokenize.COMMENT:
                blocos.append((token.start[0], token.string))
    except (tokenize.TokenError, IndentationError) as erro:
        blocos.append((1, "ERRO DE TOKENIZACAO: %s" % erro))
        return blocos

    try:
        arvore = ast.parse(origem)
    except SyntaxError as erro:
        blocos.append((erro.lineno or 1, "ERRO DE PARSE: %s" % erro))
        return blocos

    for no in ast.walk(arvore):
        if not isinstance(
            no, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
        ):
            continue
        corpo = getattr(no, "body", None)
        if not corpo:
            continue
        primeiro = corpo[0]
        if not isinstance(primeiro, ast.Expr):
            continue
        valor = primeiro.value
        if isinstance(valor, ast.Constant) and isinstance(valor.value, str):
            blocos.extend(_mapear_linhas_docstring(valor, origem.splitlines()))
    return blocos


def _mapear_linhas_docstring(valor, linhas_do_arquivo):
    """Alinha cada linha da docstring à sua linha real no arquivo.

    Contar a partir de ``lineno`` do nó AST desloca o resultado: a string
    começa na primeira aspa, pode estar na mesma linha do conteúdo e pode
    conter quebras escapadas que não ocupam linha física. Em vez de inferir,
    a posição real é confirmada comparando cada linha do valor com a linha
    fonto correspondente. Quando a comparação falha (docstring de uma linha
    só, escape no meio), vale a posição do nó: o marcador pode ser reportado
    uma linha antes ou depois, nunca omitido.
    """
    linhas_valor = valor.value.splitlines()

    # Primeira linha do arquivo, a partir do nó, que contenha a linha inicial
    # não vazia da docstring.
    inicial = next((l for l in linhas_valor if l.strip()), None)
    if inicial is None:
        return []

    ancora = (getattr(valor, "lineno", 1) or 1) - 1
    alvo = inicial.strip()
    for indice in range(max(ancora - 1, 0), len(linhas_do_arquivo)):
        if alvo in linhas_do_arquivo[indice]:
            deslocamento = indice - linhas_valor.index(inicial)
            return [
                (deslocamento + i + 1, texto)
                for i, texto in enumerate(linhas_valor)
            ]

    return [(ancora + 1 + i, texto) for i, texto in enumerate(linhas_valor)]


def varrer_py(caminho):
    achados = []
    for base, trecho in extrair_texto_py(caminho):
        for linha, marcador, texto in linhas_com_marcadores(trecho, base):
            achados.append((linha, marcador, texto))
    return achados


def varrer_texto(caminho, remover_tags=False):
    texto = ler_texto(caminho)
    if remover_tags:
        # Substitui blocos <style>/<script> por quebras de linha, para não
        # deslocar a numeração das linhas do restante do documento.
        def _limpar(match):
            return "\n" * match.group(0).count("\n")

        texto = HTML_TAGS_IGNORADAS.sub(_limpar, texto)
    return linhas_com_marcadores(texto, 1)


def alvos():
    """Lista de (rotulo, caminho, funcao_de_varredura)."""
    lista = []

    if os.path.isdir(DIR_BIBLIOTECAS):
        for nome in sorted(os.listdir(DIR_BIBLIOTECAS)):
            if nome.endswith(".py"):
                caminho = os.path.join(DIR_BIBLIOTECAS, nome)
                lista.append(
                    ("tcc_opendss/bibliotecas/" + nome, caminho, varrer_py)
                )

    lista.append(("README.md", os.path.join(RAIZ, "README.md"), varrer_texto))
    lista.append(
        (
            "tcc_opendss/hardware/README.md",
            os.path.join(RAIZ, "tcc_opendss", "hardware", "README.md"),
            varrer_texto,
        )
    )

    for nome in ("manual_usuario.html", "manual_desenvolvedor.html"):
        caminho = os.path.join(RAIZ, "doc", nome)
        lista.append(
            (
                "doc/" + nome,
                caminho,
                lambda p: varrer_texto(p, remover_tags=True),
            )
        )

    lista.append(("LICENSE.md", os.path.join(RAIZ, "LICENSE.md"), varrer_texto))
    return lista


def contar_linhas(caminho):
    try:
        return len(ler_texto(caminho).splitlines())
    except (IOError, OSError):
        return 0


def principal():
    total_marcadores = 0
    total_arquivos = 0
    arquivos_com_ocorrencia = []

    print("Verificacao de estilo — marcadores de conectivo/hedging")
    print("Diretriz: C:\\Users\\hpinheiro\\Downloads\\Diretrizes de estilo de escrita.md")
    print("")
    print("%-46s %7s %8s  %s" % ("arquivo", "linhas", "marcas", "situacao"))
    print("-" * 78)

    for rotulo, caminho, funcao in alvos():
        if not os.path.isfile(caminho):
            print("%-46s %7s %8s  AUSENTE" % (rotulo, "-", "-"))
            continue
        total_arquivos += 1
        achados = funcao(caminho)
        total_marcadores += len(achados)
        situacao = "OK" if not achados else "MARCADOR"
        print(
            "%-46s %7d %8d  %s"
            % (rotulo, contar_linhas(caminho), len(achados), situacao)
        )
        if achados:
            arquivos_com_ocorrencia.append((rotulo, achados))

    print("-" * 78)
    print("Arquivos varridos: %d" % total_arquivos)
    print("Marcadores fora das excecoes: %d" % total_marcadores)
    print("")

    print("Excecoes documentadas (nao marcadas):")
    for chave, itens in EXCECOES.items():
        for item in itens:
            print("  [%s] %s" % (chave, item))
    print("")

    if arquivos_com_ocorrencia:
        for rotulo, achados in arquivos_com_ocorrencia:
            print("Ocorrencias em %s:" % rotulo)
            for linha, marcador, texto in achados:
                print("  L%d  [%s]  %s" % (linha, marcador, texto))
        print("")
        print("VEREDITO: REPROVADO")
        return 1

    print("VEREDITO: APROVADO")
    return 0


if __name__ == "__main__":
    sys.exit(principal())
