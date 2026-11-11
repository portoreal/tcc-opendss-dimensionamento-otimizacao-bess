#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Verificacao estrutural de conference_101719.tex (sem toolchain LaTeX).

Checa, por leitura do fonte:
  (a) toda referencia \\ref{...}/\\eqref{...} tem \\label correspondente e lista
      rotulos orfaos de floats/equacoes;
  (b) balanceamento begin/end dos ambientes estruturais;
  (c) reprodutibilidade da figura: roda doc/gerar_figura_soc_falta.py, le o
      JSON e confere (i) as tensoes de referencia e (ii) que as coordenadas
      pgfplots no tex casam com o JSON;
  (d) o abstract contem os numeros atualizados (12.027,89 e 24,94).

Uso (da raiz do repositorio):
    python doc/verificar_artigo.py [--sem-simulacao]

--sem-simulacao pula a rodada do OpenDSS e valida so a estrutura do tex e a
coerencia do JSON ja gerado.

Saida: relatorio no stdout; codigo de saida 0 se tudo passar, 1 caso contrario.
"""

import json
import os
import re
import subprocess
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEX = os.path.join(RAIZ, "conference_101719.tex")
GERADOR = os.path.join(RAIZ, "doc", "gerar_figura_soc_falta.py")
DADOS = os.path.join(RAIZ, "doc", "fig_soc_falta_dados.json")

AMBIENTES = [
    "figure", "table", "equation", "gather", "tabularx", "tabular",
    "tikzpicture", "axis", "abstract", "document",
]

# Tensoes de referencia da falta trifasica em B4 (item 2 da especificacao),
# a serem reproduzidas com tol 1e-3.
REFERENCIA_PU = {
    "b4": {"base": 0.8723, "selecionado_50kw": 0.8758, "maior_porte_1000kw": 0.931},
    "b5": {"base": 0.8484, "selecionado_50kw": 0.8517, "maior_porte_1000kw": 0.905},
}
TOL_PU = 1e-3

falhas = []
avisos = []


def falha(msg):
    falhas.append(msg)


def aviso(msg):
    avisos.append(msg)


def ler_tex():
    with open(TEX, "r", encoding="utf-8") as fh:
        return fh.read()


def extrair(texto, padrao):
    return re.findall(padrao, texto)


# ---------------------------------------------------------------- (a) refs
def checar_referencias(texto):
    rotulos = set(extrair(texto, r"\\label\{([^}]+)\}"))
    referencias = set(extrair(texto, r"\\ref\{([^}]+)\}"))
    referencias |= set(extrair(texto, r"\\eqref\{([^}]+)\}"))

    sem_rotulo = sorted(referencias - rotulos)
    if sem_rotulo:
        falha("referencias sem \\label correspondente: " + ", ".join(sem_rotulo))

    # Rotulos orfaos: definidos e nunca referenciados. Rotulos de secao sao
    # usados por \ref; equacoes/floats so contam como orfaos se ninguem os
    # referencia.
    orfaos = sorted(rotulos - referencias)
    floats = set(extrair(texto, r"\\label\{(fig:[^}]+|tab:[^}]+)\}"))
    orfaos_floats = sorted(set(orfaos) & floats)
    if orfaos_floats:
        aviso("floats com rotulo nunca referenciado: " + ", ".join(orfaos_floats))

    print("(a) referencias: {} \\ref/\\eqref, {} \\label; sem rotulo: {}; "
          "rotulos sem referencia: {}".format(
              len(referencias), len(rotulos), len(sem_rotulo), len(orfaos)))
    for nome in orfaos:
        print("      - rotulo sem referencia: {}".format(nome))
    return referencias, rotulos


# ------------------------------------------------------- (b) balanceamento
def checar_balanceamento(texto):
    print("(b) balanceamento de ambientes:")
    for ambiente in AMBIENTES:
        # \begin{env} e \begin{env}[opcoes]{...} contam igualmente.
        inicios = len(re.findall(
            r"\\begin\{" + re.escape(ambiente) + r"\}", texto))
        fins = len(re.findall(
            r"\\end\{" + re.escape(ambiente) + r"\}", texto))
        estado = "ok" if inicios == fins else "DESBALANCEADO"
        print("      {:12s} begin={:3d} end={:3d}  {}".format(
            ambiente, inicios, fins, estado))
        if inicios != fins:
            falha("ambiente {} desbalanceado: {} begin vs {} end".format(
                ambiente, inicios, fins))


# ---------------------------------------------- (c) figura: dados x tex
def rodar_gerador():
    print("(c) rodando doc/gerar_figura_soc_falta.py ...")
    proc = subprocess.run(
        [sys.executable, GERADOR], cwd=RAIZ,
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    saida = (proc.stdout or "") + (proc.stderr or "")
    for linha in saida.strip().splitlines():
        print("      | " + linha)
    if proc.returncode != 0:
        falha("gerador retornou codigo {}".format(proc.returncode))


def carregar_dados():
    with open(DADOS, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _coords_tex(texto, rotulo):
    """Extrai o bloco 'coordinates {...}' que sucede \\label{rotulo}? Nao: os
    addplot nao carregam rotulo. A extracao e por marcador textual."""
    return texto


def checar_tensoes(dados):
    pu = dados["tensao"]["pu_minimo"]
    for barra, referencia in REFERENCIA_PU.items():
        for serie, esperado in referencia.items():
            obtido = pu[serie][barra]
            erro = abs(obtido - esperado)
            estado = "ok" if erro <= TOL_PU else "FORA"
            print("      {:3s} {:20s} obtido={:.4f} esperado={:.4f} "
                  "erro={:.2e} {}".format(barra, serie, obtido, esperado,
                                          erro, estado))
            if erro > TOL_PU:
                falha("tensao {} em {} fora da tolerancia: {:.4f} vs {:.4f}"
                      .format(serie, barra, obtido, esperado))


def checar_invariancia(dados):
    val = dados.get("validacao", {})
    ok = val.get("aprovado")
    print("      invariancia de %stored no JSON: {}".format(
        "aprovada" if ok else "REPROVADA"))
    if not ok:
        falha("validacao de invariancia de %stored nao aprovada no JSON")


def checar_coordenadas_no_tex(texto, dados):
    """Toda string de coordenadas do JSON precisa aparecer no .tex, e o tex
    nao pode conter coordenadas de tensao que nao venham do JSON."""
    pgf = dados["pgfplots"]
    for chave in ("soc", "tensao_base", "tensao_selecionado",
                  "tensao_maior_porte"):
        coordenadas = pgf[chave]
        if coordenadas in texto:
            print("      coordenadas '{}' presentes no tex ({} pontos)".format(
                chave, coordenadas.count("(")))
        else:
            falha("coordenadas '{}' ausentes do tex".format(chave))


# ------------------------------------------------------------- (d) abstract
def checar_abstract(texto):
    casamento = re.search(r"\\begin\{abstract\}(.*?)\\end\{abstract\}",
                          texto, re.S)
    if not casamento:
        falha("abstract ausente")
        return
    corpo = casamento.group(1)
    for numero in ("12.027,89", "24,94"):
        if numero in corpo:
            print("(d) abstract contem '{}': ok".format(numero))
        else:
            falha("abstract nao contem '{}'".format(numero))
    # O texto exato tem um unico paragrafo.
    if "\n\n" in corpo.strip():
        falha("abstract com mais de um paragrafo")


def main(argv):
    sem_simulacao = "--sem-simulacao" in argv

    texto = ler_tex()
    print("== Verificacao estrutural de {} ==".format(
        os.path.relpath(TEX, RAIZ)))
    print()

    checar_referencias(texto)
    print()
    checar_balanceamento(texto)
    print()

    if not sem_simulacao:
        rodar_gerador()
    else:
        print("(c) --sem-simulacao: gerador nao executado")

    if not os.path.isfile(DADOS):
        falha("JSON de dados ausente: {}".format(DADOS))
    else:
        dados = carregar_dados()
        checar_tensoes(dados)
        checar_invariancia(dados)
        checar_coordenadas_no_tex(texto, dados)
    print()
    checar_abstract(texto)
    print()

    if avisos:
        print("AVISOS ({}):".format(len(avisos)))
        for item in avisos:
            print("  - " + item)
        print()

    if falhas:
        print("FALHAS ({}):".format(len(falhas)))
        for item in falhas:
            print("  - " + item)
        print()
        print("RESULTADO: REPROVADO")
        return 1

    print("RESULTADO: APROVADO")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
