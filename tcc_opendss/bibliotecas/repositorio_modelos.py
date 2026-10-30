__author__ = 'Pedro Henrique Sousa Pinheiro'
"""Persistência dos modelos dimensionados (salvos por projeto, um arquivo
JSON por tipo de elemento dentro de <projeto>/dimensionamento/)."""

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
        raise ValueError(f"O tipo '{tipo}' não possui repositório de modelos dimensionados.")
    return os.path.join(pasta_dimensionamento, nome_arquivo)


def listar_modelos(pasta_dimensionamento: str, tipo: str) -> list:
    caminho = _caminho_arquivo(pasta_dimensionamento, tipo)
    if not os.path.exists(caminho):
        return []
    with open(caminho, "r", encoding="utf-8") as f:
        return json.load(f)


def salvar_modelo(pasta_dimensionamento: str, tipo: str, nome_modelo: str,
                   parametros: dict, memoria_calculo: dict) -> str:
    """Salva um novo modelo dimensionado. Se o nome já existir, é
    auto-renomeado (mesma regra usada para elementos da rede). Retorna
    o nome final efetivamente salvo."""

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
    modelos = listar_modelos(pasta_dimensionamento, tipo)
    modelos = [m for m in modelos if m["nome"] != nome_modelo]

    caminho = _caminho_arquivo(pasta_dimensionamento, tipo)
    with open(caminho, "w", encoding="utf-8") as f:
        json.dump(modelos, f, indent=2, ensure_ascii=False)