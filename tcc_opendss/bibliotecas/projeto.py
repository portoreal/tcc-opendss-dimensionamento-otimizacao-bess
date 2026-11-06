__author__ = 'Pedro Henrique Sousa Pinheiro'
"""Gerenciamento de Projetos.

Um projeto é uma pasta em disco com três subpastas, cada uma guardando um
tipo de dado do estudo: 'dimensionamento' (modelos de linha, transformador,
PV, storage etc. já calculados), 'curvas' (curvas características e
LoadShapes) e 'rede' (os arquivos .dss exportados e o rede.json com o
diagrama). Tudo o que o usuário produz fica contido ali — apagar a pasta do
projeto remove o estudo inteiro, sem sobras em outros lugares.
"""

import os
import json
from dataclasses import dataclass
from datetime import datetime
from typing import List

import sys

# TRANSPARÊNCIA TÉCNICA — onde ficam os projetos, em script ou congelado.
#   (1) Rodando como script (repositório ou .bat): OPEN_DSS_DIR é a pasta
#       "tcc_opendss", achada a partir de __file__ (este arquivo vive em
#       <...>/tcc_opendss/bibliotecas/projeto.py); os projetos do usuário
#       ficam em <...>/tcc_opendss/projetos/.
#   (2) Rodando congelado (PyInstaller --onedir, sys.frozen): não existe
#       __file__ apontando para pasta gravável. O bundle é read-only e
#       _internal/ não é lugar de dados do usuário. Por isso a distribuição
#       leva a pasta "tcc_opendss/" AO LADO do executável:
#           dist/TccOpendss/TccOpendss.exe
#           dist/TccOpendss/tcc_opendss/projetos/        <- PASTA_BASE_PROJETOS
#           dist/TccOpendss/tcc_opendss/hardware/
#           dist/TccOpendss/tcc_opendss/validacao_ieee/
#       A base sai de sys.executable, portanto, e não de __file__: é o que
#       garante pasta gravável nos dois modos.
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
    # Cria a árvore de pastas se ainda não existir. exist_ok=True deixa a
    # chamada idempotente: abrir um projeto que já está no disco não apaga
    # nem recria nada.
    os.makedirs(projeto.caminho_raiz, exist_ok=True)
    os.makedirs(projeto.caminho_dimensionamento, exist_ok=True)
    os.makedirs(projeto.caminho_curvas, exist_ok=True)
    os.makedirs(projeto.caminho_rede, exist_ok=True)

    if not os.path.exists(projeto.caminho_metadados):
        # projeto.json só é escrito na primeira abertura; daí em diante
        # preserva a data de criação original.
        metadados = {
            "nome": projeto.nome,
            "criado_em": datetime.now().isoformat(timespec="seconds"),
        }
        with open(projeto.caminho_metadados, "w", encoding="utf-8") as f:
            json.dump(metadados, f, indent=2, ensure_ascii=False)


def criar_ou_abrir_projeto_por_nome(nome: str) -> Projeto:
    # O nome vira nome de pasta, então o strip() evita a pasta " Projeto1 "
    # criada por um espaço digitado sem querer no campo de texto.
    nome = nome.strip()
    caminho = os.path.join(PASTA_BASE_PROJETOS, nome)
    projeto = Projeto(nome=nome, caminho_raiz=caminho)
    garantir_estrutura(projeto)
    return projeto


def abrir_projeto_por_caminho(caminho: str) -> Projeto:
    # normpath padroniza separadores e ".." — o mesmo projeto aberto pela
    # interface e pelo argumento de linha de comando cai no mesmo caminho.
    caminho = os.path.normpath(caminho)
    # basename vazio significa que o caminho terminou em separador; nesse
    # caso exibe-se o caminho completo em vez de um rótulo em branco.
    nome = os.path.basename(caminho) or caminho
    projeto = Projeto(nome=nome, caminho_raiz=caminho)
    garantir_estrutura(projeto)
    return projeto


def listar_projetos() -> List[str]:
    # Pasta-base ausente não é erro: na primeira execução ela ainda não
    # existe, e a lista vazia é a resposta correta.
    if not os.path.isdir(PASTA_BASE_PROJETOS):
        return []
    # Só diretórios contam; arquivos soltos na pasta-base (lixo, .gitkeep)
    # ficam de fora.
    return sorted([
        nome for nome in os.listdir(PASTA_BASE_PROJETOS)
        if os.path.isdir(os.path.join(PASTA_BASE_PROJETOS, nome))
    ])