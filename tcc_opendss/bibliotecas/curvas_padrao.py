__author__ = 'Pedro Henrique Sousa Pinheiro'
"""Curvas semanais padrão embutidas na ferramenta de otimização de BESS.

Cada natureza ('carga' e 'geracao') traz SETE curvas — uma por dia da
semana, de segunda a domingo, hora a hora (0h–23h), sempre em PERCENTUAL
do valor nominal do elemento.

POR QUE PERCENTUAL, E NÃO POTÊNCIA
    O LoadShape do OpenDSS multiplica a potência NOMINAL do elemento pelo
    multiplicador da curva (multiplicadores() = percentual/100). Como o
    percentual é adimensional, a mesma curva continua válida quando a
    potência muda: o usuário altera os kW/kvar/kVA do elemento no editor e
    o perfil inteiro escala junto, sem nenhuma edição na curva. Em potência
    absoluta, cada mudança de dimensionamento exigiria uma curva nova — foi
    esse o argumento que definiu o formato percentual.

OS PERFIS SÃO REPRESENTATIVOS, NÃO MEDIÇÕES
    Os valores abaixo reproduzem a forma de alimentadores MISTOS (comercial
    mais residencial) brasileiros, e de geração fotovoltaica em dias limpos,
    parciais e nublados. Não são séries medidas em campo nem climatologia de
    uma localidade específica. Valem como ponto de partida editável: o
    diálogo de curvas semanais permite substituir qualquer ponto, elemento a
    elemento, e voltar ao padrão quando quiser.

PONTOS FORA DE 0–100% SÃO PERMITIDOS
    A faixa 0–100% não é limite da biblioteca nem do formato. Zero é
    legítimo e comum em carga — motor de produção desligado em certo horário
    é o caso típico. Acima de 100% também vale: durante a partida, um motor
    consome mais que a própria potência nominal. As curvas padrão abaixo não
    passam de 100% porque descrevem regime permanente agregado; o módulo não
    impõe teto, e quem edita pode ultrapassar.

kW E kvar COMPARTILHAM O MESMO MULTIPLICADOR
    O LoadShape aplica o multiplicador tanto ao kW quanto ao kvar do
    elemento, o que preserva o fator de potência ao longo do dia. Uma curva
    de reativo independente da de ativo não é representável por um único
    LoadShape. Verificado no motor: shape de 50% sobre uma carga de 30 kW e
    3 kvar resulta em 15,0 kW e 1,5 kvar, com FP constante.

O módulo é SÓ DADOS — não importa Qt nem qualquer módulo de interface. É o
que permite usar as curvas tanto pela UI quanto em fluxos headless e testes.
"""

from .curvas import CurvaCaracteristica

DIAS_SEMANA = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]

NATUREZAS_VALIDAS = ("carga", "geracao")


# ---------------------------------------------------------------------------
# Curvas padrão de CARGA (alimentador misto comercial + residencial)
# ---------------------------------------------------------------------------
# A forma geral é sempre a mesma: consumo mínimo de madrugada, rampa de
# manhã entre 7h e 8h (comércio abrindo), patamar alto na hora do almoço e
# pico noturno às 19h, quando residência e comércio ainda se sobrepõem.
# Sábado atrasa o início e estica o lazer noturno — daí o 100% também às 20h.
# Domingo é o dia deprimido: atividade comercial baixa, com um pico de almoço
# tardio e outro no jantar.
_CARGA_SEGUNDA = [
    (0, 35), (1, 32), (2, 30), (3, 30), (4, 33), (5, 40),
    (6, 52), (7, 62), (8, 72), (9, 80), (10, 86), (11, 90),
    (12, 94), (13, 88), (14, 86), (15, 88), (16, 88), (17, 90),
    (18, 96), (19, 100), (20, 95), (21, 86), (22, 70), (23, 50),
]

_CARGA_TERCA = [
    (0, 35), (1, 32), (2, 30), (3, 30), (4, 32), (5, 38),
    (6, 50), (7, 65), (8, 75), (9, 82), (10, 88), (11, 92),
    (12, 95), (13, 90), (14, 88), (15, 90), (16, 88), (17, 88),
    (18, 95), (19, 100), (20, 96), (21, 88), (22, 72), (23, 52),
]

_CARGA_QUARTA = [
    (0, 35), (1, 32), (2, 30), (3, 30), (4, 32), (5, 38),
    (6, 50), (7, 64), (8, 76), (9, 83), (10, 88), (11, 93),
    (12, 96), (13, 91), (14, 89), (15, 91), (16, 89), (17, 89),
    (18, 95), (19, 100), (20, 96), (21, 87), (22, 71), (23, 51),
]

_CARGA_QUINTA = [
    (0, 34), (1, 31), (2, 30), (3, 30), (4, 32), (5, 38),
    (6, 50), (7, 64), (8, 75), (9, 83), (10, 88), (11, 92),
    (12, 95), (13, 90), (14, 88), (15, 90), (16, 88), (17, 88),
    (18, 95), (19, 100), (20, 96), (21, 88), (22, 72), (23, 52),
]

# Sexta: o comércio encerra mais cedo, mas a noite vai mais longe (pico 98 às 19h).
_CARGA_SEXTA = [
    (0, 36), (1, 33), (2, 31), (3, 30), (4, 32), (5, 38),
    (6, 48), (7, 62), (8, 74), (9, 82), (10, 87), (11, 90),
    (12, 93), (13, 88), (14, 85), (15, 86), (16, 84), (17, 86),
    (18, 94), (19, 98), (20, 96), (21, 90), (22, 78), (23, 60),
]

# Sábado: início tardio (8h em 58%) e pico de lazer entre 19h e 20h.
_CARGA_SABADO = [
    (0, 38), (1, 35), (2, 33), (3, 32), (4, 32), (5, 35),
    (6, 42), (7, 50), (8, 58), (9, 68), (10, 76), (11, 82),
    (12, 88), (13, 90), (14, 90), (15, 88), (16, 88), (17, 90),
    (18, 96), (19, 100), (20, 100), (21, 95), (22, 88), (23, 72),
]

# Domingo: dia deprimido (máximo diurno de 68% às 12h) e pico de jantar às 20h.
_CARGA_DOMINGO = [
    (0, 36), (1, 33), (2, 31), (3, 30), (4, 31), (5, 33),
    (6, 36), (7, 38), (8, 40), (9, 45), (10, 52), (11, 60),
    (12, 68), (13, 62), (14, 55), (15, 50), (16, 50), (17, 58),
    (18, 75), (19, 90), (20, 92), (21, 78), (22, 58), (23, 44),
]

CARGA_SEMANA_PADRAO = {
    "Segunda": _CARGA_SEGUNDA,
    "Terça": _CARGA_TERCA,
    "Quarta": _CARGA_QUARTA,
    "Quinta": _CARGA_QUINTA,
    "Sexta": _CARGA_SEXTA,
    "Sábado": _CARGA_SABADO,
    "Domingo": _CARGA_DOMINGO,
}


# ---------------------------------------------------------------------------
# Curvas padrão de GERAÇÃO (sino fotovoltaico, sem rastreamento)
# ---------------------------------------------------------------------------
# Zero entre 19h e 5h; pico entre 12h e 13h. A variação entre os dias não é
# aleatória: reproduz condições de céu realistas — limpo, parcial (nuvens
# passageiras) e nublado. A forma do sino se mantém; o que muda é a altura,
# que é exatamente o efeito de uma nuvem sobre a geração.
# Segunda / Quarta / Sexta: céu limpo, pico 100 às 13h.

_GERACAO_LIMPA = [
    (0, 0), (1, 0), (2, 0), (3, 0), (4, 0), (5, 0),
    (6, 2), (7, 10), (8, 25), (9, 45), (10, 68), (11, 86),
    (12, 95), (13, 100), (14, 97), (15, 85), (16, 65), (17, 42),
    (18, 20), (19, 5), (20, 0), (21, 0), (22, 0), (23, 0),
]

# Terça: céu parcial, pico 78 às 13h.
_GERACAO_TERCA = [
    (0, 0), (1, 0), (2, 0), (3, 0), (4, 0), (5, 0),
    (6, 2), (7, 8), (8, 20), (9, 35), (10, 53), (11, 67),
    (12, 74), (13, 78), (14, 76), (15, 66), (16, 51), (17, 33),
    (18, 16), (19, 4), (20, 0), (21, 0), (22, 0), (23, 0),
]

# Quinta: nublado, pico 55 às 13h.
_GERACAO_QUINTA = [
    (0, 0), (1, 0), (2, 0), (3, 0), (4, 0), (5, 0),
    (6, 1), (7, 6), (8, 14), (9, 25), (10, 37), (11, 47),
    (12, 52), (13, 55), (14, 53), (15, 47), (16, 36), (17, 23),
    (18, 11), (19, 3), (20, 0), (21, 0), (22, 0), (23, 0),
]

# Sábado: limpo com cirros, pico 93 às 13h.
_GERACAO_SABADO = [
    (0, 0), (1, 0), (2, 0), (3, 0), (4, 0), (5, 0),
    (6, 2), (7, 9), (8, 23), (9, 42), (10, 63), (11, 80),
    (12, 88), (13, 93), (14, 90), (15, 79), (16, 61), (17, 39),
    (18, 19), (19, 5), (20, 0), (21, 0), (22, 0), (23, 0),
]

# Domingo: parcial, pico 82 às 13h.
_GERACAO_DOMINGO = [
    (0, 0), (1, 0), (2, 0), (3, 0), (4, 0), (5, 0),
    (6, 2), (7, 8), (8, 21), (9, 37), (10, 56), (11, 71),
    (12, 79), (13, 82), (14, 80), (15, 70), (16, 54), (17, 35),
    (18, 16), (19, 4), (20, 0), (21, 0), (22, 0), (23, 0),
]

GERACAO_SEMANA_PADRAO = {
    "Segunda": _GERACAO_LIMPA,
    "Terça": _GERACAO_TERCA,
    "Quarta": _GERACAO_LIMPA,
    "Quinta": _GERACAO_QUINTA,
    "Sexta": _GERACAO_LIMPA,
    "Sábado": _GERACAO_SABADO,
    "Domingo": _GERACAO_DOMINGO,
}


def obter_pontos_padrao(natureza: str, dia: str):
    """Devolve os 24 pontos (hora, percentual) padrão da natureza e do dia.

    Natureza ou dia inválido levanta ValueError com mensagem explícita. A
    escolha é deliberada: devolver lista vazia faria o erro aparecer longe
    daqui, como uma curva sem pontos no gráfico sem que ninguém soubesse
    por quê.
    """
    if natureza not in NATUREZAS_VALIDAS:
        raise ValueError(
            f"Natureza invalida: {natureza!r}. "
            f"Use 'carga' ou 'geracao'."
        )
    if dia not in DIAS_SEMANA:
        raise ValueError(
            f"Dia invalido: {dia!r}. "
            f"Use um de {DIAS_SEMANA}."
        )

    tabela = CARGA_SEMANA_PADRAO if natureza == "carga" else GERACAO_SEMANA_PADRAO
    return list(tabela[dia])


def criar_curva_padrao(nome: str, natureza: str, dia: str) -> CurvaCaracteristica:
    """Monta uma CurvaCaracteristica 'daily' de 24 pontos com os valores
    padrão da natureza e do dia informados.

    É o que sustenta o botão "retornar ao padrão" do diálogo de curvas
    semanais. Quem chama precisa gravar o retorno com atualizar_curva() —
    a função apenas constrói o objeto em memória e não toca no repositório.
    """
    pontos = obter_pontos_padrao(natureza, dia)
    return CurvaCaracteristica(
        nome=nome,
        natureza=natureza,
        modo="daily",
        duracao_minutos=None,
        pontos=pontos,
    )
