__author__ = 'Pedro Henrique Sousa Pinheiro'
"""Persistência dos modelos dimensionados.

Cada projeto guarda seus modelos em <projeto>/dimensionamento/, um arquivo
JSON por tipo de elemento. A separação por tipo é deliberada: duas telas
diferentes podem editar linhas e transformadores ao mesmo tempo sem uma
sobrescrever o trabalho da outra.
"""

import os
import json
from datetime import datetime

from .modelo_rede import gerar_nome_unico


NOME_ARQUIVO_POR_TIPO = {
    "Line": "linhas.json",
    "Transformer": "transformadores.json",
    "PVSystem": "pvsystems.json",
    "Storage": "storage.json",
    "Capacitor": "capacitores.json",
    "Generator": "geradores.json",
}


def _caminho_arquivo(pasta_dimensionamento: str, tipo: str) -> str:
    nome_arquivo = NOME_ARQUIVO_POR_TIPO.get(tipo)
    if not nome_arquivo:
        # Exceção em vez de None: um tipo sem repositório é erro de
        # programação, e falhar cedo aponta a linha que chamou.
        raise ValueError(f"O tipo '{tipo}' não possui repositório de modelos dimensionados.")
    return os.path.join(pasta_dimensionamento, nome_arquivo)


def listar_modelos(pasta_dimensionamento: str, tipo: str) -> list:
    caminho = _caminho_arquivo(pasta_dimensionamento, tipo)
    # Arquivo ainda não criado é o estado normal de um projeto novo —
    # lista vazia, não exceção.
    if not os.path.exists(caminho):
        return []
    with open(caminho, "r", encoding="utf-8") as f:
        return json.load(f)


def salvar_modelo(pasta_dimensionamento: str, tipo: str, nome_modelo: str,
                   parametros: dict, memoria_calculo: dict) -> str:
    """Salva um novo modelo dimensionado e devolve o nome efetivamente usado.

    Nome repetido é auto-renomeado (mesma regra aplicada aos elementos da
    rede), de modo que salvar duas vezes o mesmo cálculo gera dois modelos
    distintos em vez de substituir o anterior. Quem chama deve exibir o
    retorno: o nome salvo pode não ser o que o usuário digitou.
    """

    modelos = listar_modelos(pasta_dimensionamento, tipo)
    nomes_existentes = [m["nome"] for m in modelos]
    nome_final = gerar_nome_unico(nome_modelo, nomes_existentes)

    modelos.append({
        "nome": nome_final,
        "tipo": tipo,
        "parametros": parametros,
        "memoria_calculo": memoria_calculo,
        "criado_em": datetime.now().isoformat(timespec="seconds"),
    })

    os.makedirs(pasta_dimensionamento, exist_ok=True)
    caminho = _caminho_arquivo(pasta_dimensionamento, tipo)
    with open(caminho, "w", encoding="utf-8") as f:
        json.dump(modelos, f, indent=2, ensure_ascii=False)

    return nome_final


def remover_modelo(pasta_dimensionamento: str, tipo: str, nome_modelo: str):
    # Remove por nome e regrava o JSON inteiro. Não há índice nem
    # transação: um nome inexistente simplesmente não altera nada.
    modelos = listar_modelos(pasta_dimensionamento, tipo)
    modelos = [m for m in modelos if m["nome"] != nome_modelo]

    caminho = _caminho_arquivo(pasta_dimensionamento, tipo)
    with open(caminho, "w", encoding="utf-8") as f:
        json.dump(modelos, f, indent=2, ensure_ascii=False)