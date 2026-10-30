__author__ = 'Pedro Henrique Sousa Pinheiro'
"""Gerenciamento de Projetos: cada projeto é uma pasta contendo as
subpastas 'dimensionamento' (modelos calculados), 'curvas' (curvas
características/LoadShapes) e 'rede' (arquivos .dss e rede.json)."""

import os
import json
from dataclasses import dataclass
from datetime import datetime
from typing import List

import sys

# TRANSPARÊNCIA TÉCNICA — raiz do projeto em modo script vs. congelado.
#   (1) Script (repositório / .bat): OPEN_DSS_DIR é a PASTA "tcc_opendss",
#       resolvida por __file__ (este arquivo vive em
#       <...>/tcc_opendss/bibliotecas/projeto.py), e os projetos do usuário
#       ficam em <...>/tcc_opendss/projetos/.
#   (2) Congelado (PyInstaller --onedir, sys.frozen): não existe __file__
#       apontando para uma pasta gravável — o bundle é read-only e
#       _internal/ não é lugar de dados do usuário. A distribuição leva a
#       pasta de dados "tcc_opendss/" AO LADO do executável:
#           dist/TccOpendss/TccOpendss.exe
#           dist/TccOpendss/tcc_opendss/projetos/        <- PASTA_BASE_PROJETOS
#           dist/TccOpendss/tcc_opendss/hardware/
#           dist/TccOpendss/tcc_opendss/validacao_ieee/
#       Daí a base ser derivada de sys.executable, e não de __file__.
_CONGELADO = bool(getattr(sys, "frozen", False))

if _CONGELADO:
    OPEN_DSS_DIR = os.path.join(os.path.dirname(os.path.abspath(sys.executable)), "tcc_opendss")
else:
    OPEN_DSS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PASTA_BASE_PROJETOS = os.path.join(OPEN_DSS_DIR, "projetos")


@dataclass
class Projeto:
    nome: str
    caminho_raiz: str

    @property
    def caminho_dimensionamento(self) -> str:
        return os.path.join(self.caminho_raiz, "dimensionamento")

    @property
    def caminho_curvas(self) -> str:
        return os.path.join(self.caminho_raiz, "curvas")

    @property
    def caminho_rede(self) -> str:
        return os.path.join(self.caminho_raiz, "rede")

    @property
    def caminho_metadados(self) -> str:
        return os.path.join(self.caminho_raiz, "projeto.json")


def garantir_estrutura(projeto: Projeto):
    os.makedirs(projeto.caminho_raiz, exist_ok=True)
    os.makedirs(projeto.caminho_dimensionamento, exist_ok=True)
    os.makedirs(projeto.caminho_curvas, exist_ok=True)
    os.makedirs(projeto.caminho_rede, exist_ok=True)

    if not os.path.exists(projeto.caminho_metadados):
        metadados = {
            "nome": projeto.nome,
            "criado_em": datetime.now().isoformat(timespec="seconds"),
        }
        with open(projeto.caminho_metadados, "w", encoding="utf-8") as f:
            json.dump(metadados, f, indent=2, ensure_ascii=False)


def criar_ou_abrir_projeto_por_nome(nome: str) -> Projeto:
    nome = nome.strip()
    caminho = os.path.join(PASTA_BASE_PROJETOS, nome)
    projeto = Projeto(nome=nome, caminho_raiz=caminho)
    garantir_estrutura(projeto)
    return projeto


def abrir_projeto_por_caminho(caminho: str) -> Projeto:
    caminho = os.path.normpath(caminho)
    nome = os.path.basename(caminho) or caminho
    projeto = Projeto(nome=nome, caminho_raiz=caminho)
    garantir_estrutura(projeto)
    return projeto


def listar_projetos() -> List[str]:
    if not os.path.isdir(PASTA_BASE_PROJETOS):
        return []
    return sorted([
        nome for nome in os.listdir(PASTA_BASE_PROJETOS)
        if os.path.isdir(os.path.join(PASTA_BASE_PROJETOS, nome))
    ])