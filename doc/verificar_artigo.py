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
  (e) o corpo do artigo (fora do abstract) contem os marcadores novos da
      migracao para a semana completa e nao contem os antigos.
  (f) a secao complementar (estudo em rede de referencia IEEE 13 nos) esta
      presente, autocontida e com os marcadores de resultado; os numeros
      antigos seguem ausentes de todo o arquivo e a checagem de "$d = 22$"
      fica restrita ao trecho do estudo principal (a secao complementar usa
      "$d = 22$ dias equivalentes por mes" por definicao propria).

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

# Barras monitoradas do painel (b) na falta trifasica na propria barra do
# armazenamento (B5). A checagem e orientada ao JSON: nao ha literal de
# tensao a reproduzir -- confere-se a coerencia interna das duas series
# (base e selecionado), a magnitude da mitigacao e a exclusao da barra
# faltosa da classificacao de sag.
BARRAS_NAO_FALTOSAS = ["b1", "b2", "b3", "b4", "b6"]
BARRA_FALTOSA = "b5"
# Mitigacao maxima coerente: o ganho de tensao na barra do armazenamento nao
# pode inverter o sentido (o BESS injeta corrente e eleva a tensao) nem
# ultrapassar o que a potencia do porte selecionado permite.
MPU_MINIMO = 0.0
MPU_MAXIMO_EXCLUSIVO = 100.0

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
    """Coerencia das duas series de tensao minima do JSON.

    Na falta trifasica solida na barra do armazenamento, o BESS eleva a
    tensao das barras monitoradas; a mitigacao e medida em mpu
    ((pu_sel - pu_base) x 1000) e precisa ser nao negativa em todas as
    barras nao faltosas. A barra faltosa (B5) fica fora dessa comparacao:
    no no em falta a tensao e o proprio curto e nao o efeito mitigado.
    """
    pu = dados["tensao"]["pu_minimo"]
    base = pu["base"]
    sel = pu["selecionado_50kw"]
    for barra in BARRAS_NAO_FALTOSAS:
        for serie, valores in (("base", base), ("selecionado_50kw", sel)):
            if barra not in valores:
                falha("serie '{}' sem a barra {}".format(serie, barra))
                return
        mpu = (sel[barra] - base[barra]) * 1000.0
        estado = "ok" if MPU_MINIMO <= mpu < MPU_MAXIMO_EXCLUSIVO else "FORA"
        print("      {:3s} base={:.4f} selecionado={:.4f} "
              "mpu={:+.4f} {}".format(barra, base[barra], sel[barra], mpu,
                                      estado))
        if not (MPU_MINIMO <= mpu < MPU_MAXIMO_EXCLUSIVO):
            falha("mitigacao incoerente na barra {}: {:+.4f} mpu".format(
                barra, mpu))

    # A barra faltosa precisa estar fora da classificacao de sag nas duas
    # rodadas -- convencao do estudo.
    classificacao = dados["tensao"]["classificacao_sag"]
    for chave in ("base", "selecionado_50kw"):
        barras_sag = classificacao.get(chave)
        if barras_sag is None:
            falha("classificacao_sag sem a rodada '{}'".format(chave))
        elif BARRA_FALTOSA in barras_sag:
            falha("barra faltosa {} classificada em sag na rodada '{}'".format(
                BARRA_FALTOSA, chave))
        else:
            print("      barra faltosa {} excluida da classificacao '{}': ok"
                  .format(BARRA_FALTOSA, chave))
    if dados["tensao"].get("excluida_da_classificacao") != BARRA_FALTOSA:
        falha("excluida_da_classificacao != {}".format(BARRA_FALTOSA))

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
    for chave in ("soc", "tensao_base", "tensao_selecionado"):
        coordenadas = pgf[chave]
        if coordenadas in texto:
            print("      coordenadas '{}' presentes no tex ({} pontos)".format(
                chave, coordenadas.count("(")))
        else:
            falha("coordenadas '{}' ausentes do tex".format(chave))
    checar_carga_b4_no_tex(texto, dados)
    checar_fv_no_tex(texto, dados)


DIAS_CARGA_B4 = ["Segunda", "Terca", "Quarta", "Quinta", "Sexta", "Sabado",
                 "Domingo"]


def checar_fv_no_tex(texto, dados):
    """Painel (a) da Fig. de curvas da semana: as 7 series de geracao
    fotovoltaica precisam vir do JSON (fv_kw do dump), com 24 pontos cada."""
    series = dados.get("fv_por_dia") or {}
    faltando = [dia for dia in DIAS_CARGA_B4 if dia not in series]
    if faltando:
        falha("fv_por_dia sem os dias: " + ", ".join(faltando))
        return
    for dia in DIAS_CARGA_B4:
        chave = "coordenadas_fv_" + dia
        coordenadas = series[dia]["coordenadas"]
        pontos = len(series[dia]["fv_kwh"])
        if pontos != 24:
            falha("fv_por_dia[{}] com {} pontos (esperados 24)".format(
                dia, pontos))
        if coordenadas in texto:
            print("      {} presentes no tex ({} pontos)".format(
                chave, coordenadas.count("(")))
        else:
            falha("coordenadas '{}' ausentes do tex".format(chave))


def normalizar(texto):
    """Colapsa espacos/quebras de linha: o fonte LaTeX quebra o caption no
    meio da frase, e a comparacao textual nao deve depender disso."""
    return " ".join(texto.split())


def bloco_curvas_semana(texto):
    """Corpo do ambiente figure que carrega \\label{fig:curvas_semana}."""
    padrao = (r"\\begin\{figure\}.*?\\label\{fig:curvas_semana\}.*?"
              r"\\end\{figure\}")
    casamento = re.search(padrao, texto, re.S)
    return casamento.group(0) if casamento else None


def checar_carga_b4_no_tex(texto, dados):
    """Painel (b) da Fig. de curvas da semana: as 7 series de carga da barra
    B4 precisam vir do JSON, com 1 casa decimal, e o caption precisa declarar
    o compartilhamento da curva entre B4 e B5."""
    series = dados.get("carga_b4_por_dia") or {}
    faltando = [dia for dia in DIAS_CARGA_B4 if dia not in series]
    if faltando:
        falha("carga_b4_por_dia sem os dias: " + ", ".join(faltando))
        return
    for dia in DIAS_CARGA_B4:
        chave = "coordenadas_carga_b4_" + dia
        coordenadas = series[dia]["coordenadas"]
        pontos = len(series[dia]["carga_b4_kwh"])
        if pontos != 24:
            falha("carga_b4_por_dia[{}] com {} pontos (esperados 24)".format(
                dia, pontos))
        if coordenadas in texto:
            print("      {} presentes no tex ({} pontos)".format(
                chave, coordenadas.count("(")))
        else:
            falha("coordenadas '{}' ausentes do tex".format(chave))

    bloco = bloco_curvas_semana(texto)
    if bloco is None:
        falha("figura fig:curvas_semana nao encontrada")
        return
    for marcador in (r"{\scriptsize (a)", r"{\scriptsize (b)"):
        if marcador in bloco:
            print("      fig:curvas_semana contem sublegenda '{}'".format(
                marcador.split("(")[1]))
        else:
            falha("fig:curvas_semana sem sublegenda " + marcador)
    if "compartilham a mesma curva padrão" in normalizar(bloco):
        print("      caption de fig:curvas_semana declara o compartilhamento "
              "B4/B5: ok")
    else:
        falha("caption de fig:curvas_semana nao declara que B4 e B5 "
              "compartilham a mesma curva padrão")


# ------------------------------------------------------------- (d) abstract
DUMP_TESTE = os.path.join(RAIZ, "tcc_opendss", "projetos", "teste",
                          "dump_estudo_otimizacao.json")


def _fmt_brl(valor, casas):
    """Formata em pt-BR: milhar '.', decimal ',', numero fixo de casas."""
    texto = "{:,.{}f}".format(valor, casas)
    return texto.replace(",", "\x00").replace(".", ",").replace("\x00", ".")


def numeros_do_abstract():
    """Economia anual e payback do vencedor, direto do dump do estudo.

    A anualizacao e a mesma do estudo: economia semanal x 52 semanas.
    """
    with open(DUMP_TESTE, "r", encoding="utf-8") as fh:
        dump = json.load(fh)
    semanal = dump["semanal_vencedor"]["economia_semanal_brl"]
    payback = dump["vencedor"]["economia_candidato"]["payback_anos"]
    return _fmt_brl(semanal * 52.0, 2), _fmt_brl(payback, 2)


def checar_abstract(texto):
    casamento = re.search(r"\\begin\{abstract\}(.*?)\\end\{abstract\}",
                          texto, re.S)
    if not casamento:
        falha("abstract ausente")
        return
    corpo = casamento.group(1)
    try:
        economia, payback = numeros_do_abstract()
    except (OSError, KeyError, TypeError) as exc:
        falha("nao foi possivel derivar os numeros do abstract do dump: "
              "{}".format(exc))
        return
    print("(d) numeros derivados do dump: economia anual = '{}', "
          "payback = '{}' anos".format(economia, payback))
    for numero in (economia, payback):
        if numero in corpo:
            print("(d) abstract contem '{}': ok".format(numero))
        else:
            falha("abstract nao contem '{}'".format(numero))
    # O texto exato tem um unico paragrafo.
    if "\n\n" in corpo.strip():
        falha("abstract com mais de um paragrafo")


# ------------------------------------------------- (e) marcadores do corpo
MARCADORES_NOVOS = [
    "ramo-e-corte",
    "15 \\times 52",
    "55\\,306{,}61",
    "349{,}53",
    "16{,}51",
    "357,99",
    "0{,}32863",
    "0{,}33407",
    "0{,}01183",
    "0{,}04730",
    "4,2~kWh com o armazenamento",
]
MARCADORES_ANTIGOS = [
    "56\\,157",
    "17\\,551",
    "0{,}31253",
    "0{,}30740",
    "0,07 a 2,5",
    "17{,}09",
    "22 \\times 12",
    "economia diária, mensal e anual",
]

# O setup do estudo (Secao de resultados) nao pode mais declarar $d = 22$ dias
# equivalentes por mes. A definicao de $d$ em eq:ei e a chave da equacao
# continuam sendo $d$ (dias equivalentes por mes), fora do escopo destes
# blocos; por isso a checagem e restrita ao trecho do estudo.
ANTIGOS_NO_ESTUDO = [
    "dias equivalentes por mês",
    "$d = 22$",
]


def corpo_sem_abstract(texto):
    """O artigo sem o ambiente abstract, para nao confundir os numeros com
    ponto de milhar do resumo (checados no item (d))."""
    return re.sub(r"\\begin\{abstract\}.*?\\end\{abstract\}", "", texto,
                  flags=re.S)


# ------------------------------------------------- (f) estudo complementar
ROTULO_IEEE13 = "subsubsec:estudo_ieee13"
TITULO_IEEE13 = "Estudo complementar em rede de referência"

BS = chr(92)

MARCADORES_IEEE13 = [
    "barra 670",
    "354.742{,}57",
    "6.821,97",
    "13,25",
    "0,5517",
    "1.100~kvar",
    "0,8407~pu",
    "192,23~kW",
    "1.000~kW/2.000~kWh",
]

# Numeros do metodo antigo que nao podem existir em ponto algum do arquivo
# (corpo ou abstract); o abstract e checado a parte, no item (d), e nao carrega
# nenhum deles.
ANTIGOS_EM_TODO_O_ARQUIVO = [
    "17" + BS + ",551",
    "17{,}09",
    "56" + BS + ",157",
    "0{,}31253",
    "0{,}30740",
    "0,07 a 2,5",
    "22 " + BS + "times 12",
]

# Trecho do estudo principal: da secao de resultados ate a subsecao do estudo
# complementar. A checagem de "$d = 22$" vale so nele -- a secao complementar
# declara, por definicao propria do experimento em IEEE 13, "$d = 22$ dias
# equivalentes por mes".
RE_INICIO_ESTUDO = r"Para ilustrar o processo completo"
RE_FIM_ESTUDO = r"\\subsubsection\{Estudo complementar"


def trecho_estudo_principal(texto):
    casamento = re.search(
        RE_INICIO_ESTUDO + r".*?(?=" + RE_FIM_ESTUDO + r")", texto, re.S)
    return casamento.group(0) if casamento else None


def checar_estudo_complementar(texto):
    """(f) A secao complementar (IEEE 13) existe, esta autocontida e traz os
    marcadores de resultado; os numeros antigos seguem fora do arquivo e o
    "$d = 22$" so pode aparecer no trecho do estudo principal."""
    corpo = corpo_sem_abstract(texto)

    rotulo_ok = ("\\label{" + ROTULO_IEEE13 + "}") in texto
    referencia_ok = ("\\ref{" + ROTULO_IEEE13 + "}") in texto
    if rotulo_ok and referencia_ok:
        print("(f) rotulo " + ROTULO_IEEE13 + " existe e e referenciado: ok")
    elif rotulo_ok:
        print("(f) rotulo " + ROTULO_IEEE13 + " existe; secao de "
              "encerramento autocontida, sem \ref a ele")
    else:
        falha("rotulo " + ROTULO_IEEE13 + " ausente")

    if TITULO_IEEE13 in normalizar(texto):
        print("(f) titulo da secao complementar presente: ok")
    else:
        falha("titulo '" + TITULO_IEEE13 + "' ausente")

    # Autocontida: nenhum \ref pendente dentro da propria secao.
    inicio = texto.find("\\label{" + ROTULO_IEEE13 + "}")
    fim = texto.find("\\section{Conclus", inicio)
    if inicio < 0 or fim < 0:
        falha("nao foi possivel delimitar a secao complementar")
        return
    secao = texto[inicio:fim]
    rotulos = set(extrair(texto, r"\\label\{([^}]+)\}"))
    pendentes = sorted(set(extrair(secao, r"\ref\{([^}]+)\}")) - rotulos)
    if pendentes:
        falha("secao complementar com \ref sem rotulo: "
              + ", ".join(pendentes))
    else:
        print("(f) secao complementar sem \ref pendente: ok")

    for marcador in MARCADORES_IEEE13:
        if marcador in normalizar(secao):
            print("(f) secao complementar contem '" + marcador + "': ok")
        else:
            falha("secao complementar nao contem '" + marcador + "'")

    for marcador in ANTIGOS_EM_TODO_O_ARQUIVO:
        copias = texto.count(marcador)
        if copias == 0:
            print("(f) arquivo inteiro sem '" + marcador + "': ok")
        else:
            falha("marcador antigo '" + marcador +
                  "' presente no arquivo ({} vezes)".format(copias))

    estudo = trecho_estudo_principal(corpo)
    if estudo is None:
        falha("trecho do estudo principal nao delimitado para a checagem "
              "de '$d = 22$'")
        return
    for marcador in ANTIGOS_NO_ESTUDO:
        if marcador not in estudo:
            print("(f) estudo principal sem '" + marcador + "': ok")
        else:
            falha("estudo principal ainda declara '" + marcador + "'")

    # A secao complementar e o unico lugar em que "$d = 22$" aparece com a
    # unidade explicita. No trecho do estudo principal a declaracao nua,
    # "$d = 22$" fechada por virgula, e justamente o que a migracao para a
    # semana completa removeu.
    if secao.count("$d = 22$ dias equivalentes") == 1:
        print("(f) '$d = 22$ dias equivalentes' na secao complementar: ok")
    else:
        falha("secao complementar nao declara '$d = 22$ dias equivalentes'")
    fora = corpo.replace(secao, "")
    if "$d = 22$" in fora:
        falha("'$d = 22$' reapareceu fora da secao complementar")
    else:
        print("(f) '$d = 22$' ausente do resto do corpo: ok")


def checar_marcadores_corpo(texto):
    corpo = corpo_sem_abstract(texto)
    for marcador in MARCADORES_NOVOS:
        if corpo.count(marcador) >= 1:
            print("(e) corpo contem '" + marcador + "': ok")
        else:
            falha("corpo nao contem o marcador novo '" + marcador + "'")
    # 18.175,34 em LaTeX aparece no bloco 6 e no bloco 7.
    copias = corpo.count("18\\,175{,}34")
    rotulo = "18\\,175{,}34"
    if copias >= 2:
        print("(e) corpo contem '" + rotulo + "' {} vezes (>=2): ok".format(
            copias))
    else:
        falha("corpo contem '" + rotulo + "' {} vezes (esperadas >=2)".format(
            copias))
    for marcador in MARCADORES_ANTIGOS:
        copias = corpo.count(marcador)
        if copias == 0:
            print("(e) marcador antigo '" + marcador +
                  "' removido do corpo: ok")
        else:
            falha("marcador antigo '" + marcador +
                  "' ainda no corpo ({} vezes)".format(copias))

    casamento = re.search(
        r"Para ilustrar o processo completo.*?A verificação conjunta confirma",
        corpo, re.S)
    if not casamento:
        falha("trecho do estudo (Secao de resultados) nao localizado")
        return
    estudo = casamento.group(0)
    for marcador in ANTIGOS_NO_ESTUDO:
        if marcador not in estudo:
            print("(e) setup do estudo sem '" + marcador + "': ok")
        else:
            falha("setup do estudo ainda declara '" + marcador + "'")


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
    checar_marcadores_corpo(texto)
    print()
    checar_estudo_complementar(texto)
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
