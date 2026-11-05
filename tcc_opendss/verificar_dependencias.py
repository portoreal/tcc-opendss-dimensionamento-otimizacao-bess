import importlib.metadata
import subprocess
import sys


# ============================================
# Dependências necessárias para o projeto
# ============================================

# PySide6: interface gráfica do módulo de Validação do Modelo Computacional
#          (padrão visual Win11/Fluent, adotado do projeto de referência).
# openpyxl: geração da planilha Excel de resultados da validação.
#
# As versões são fixadas (pin) de propósito: garante que uma instalação
# nova reproduza exatamente o requirements.txt. Em especial, o PuLP deve
# permanecer na série 2.x, pois o módulo de otimização
# (otimizacao_milp.py) usa a API clássica (LpVariable.dicts, LpStatus,
# PULP_CBC_CMD), removida na reescrita 4.x.
DEPENDENCIAS_NECESSARIAS = [
    "dss-python==0.15.7",
    "matplotlib==3.11.2",
    "pulp==2.7.0",
    "PySide6==6.12.0",
    "openpyxl==3.1.5",
]


def obter_versao_instalada(pacote: str):
    """
    Retorna a versão instalada do pacote.
    Aceita tanto o nome puro ("pulp") quanto o spec com pin
    ("pulp==2.7.0") — a consulta ao importlib.metadata usa apenas o
    nome base.
    Retorna None quando o pacote não está instalado.
    """
    nome_base = pacote.split("==")[0]

    try:
        return importlib.metadata.version(nome_base)
    except importlib.metadata.PackageNotFoundError:
        return None


def instalar_pacote(pacote: str):
    """
    Instala um pacote utilizando o pip do ambiente virtual ativo.
    O spec recebido (ex.: "pulp==2.7.0") é repassado ao pip com o pin,
    de modo que a versão fixada seja respeitada.
    """
    print(f"[INSTALANDO] {pacote}...")

    resultado = subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            pacote,
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    if resultado.returncode != 0:
        print(f"[ERRO] Falha ao instalar '{pacote}'.")
        print(resultado.stderr)
        return False

    print(f"[OK] '{pacote}' instalado com sucesso.")
    return True


def verificar_e_instalar_dependencias():
    """
    Verifica todas as dependências e instala as que estiverem faltando.
    """
    print("=" * 60)
    print(" Verificando dependências do projeto...")
    print("=" * 60)

    pacotes_instalados = {}
    pacotes_faltantes = []

    for pacote in DEPENDENCIAS_NECESSARIAS:
        versao = obter_versao_instalada(pacote)

        if versao:
            print(
                f"[OK] {pacote} já instalado "
                f"(versão {versao})."
            )
            pacotes_instalados[pacote] = versao
        else:
            print(
                f"[FALTANDO] {pacote} não está instalado."
            )
            pacotes_faltantes.append(pacote)

    if pacotes_faltantes:
        print()
        print("=" * 60)
        print(" Instalando dependências faltantes...")
        print("=" * 60)

        for pacote in pacotes_faltantes:
            sucesso = instalar_pacote(pacote)

            if not sucesso:
                print(
                    f"[ERRO] Não foi possível instalar "
                    f"'{pacote}'."
                )
                continue

            versao = obter_versao_instalada(pacote)

            if versao:
                pacotes_instalados[pacote] = versao

    else:
        print()
        print(
            "[OK] Todas as dependências já estavam instaladas."
        )

    return pacotes_instalados


def gerar_requirements(
    pacotes_instalados: dict,
    caminho_saida: str = "requirements.txt",
):
    """
    Gera o requirements.txt na pasta do projeto.
    As linhas saem sempre como "nome==versao_instalada": o nome base é
    extraído da chave (que pode vir com pin, ex.: "pulp==2.7.0") para
    não duplicar o operador (evita "pulp==2.7.0==2.7.0").
    """
    print()
    print("=" * 60)
    print(f" Gerando '{caminho_saida}'...")
    print("=" * 60)

    with open(
        caminho_saida,
        "w",
        encoding="utf-8",
    ) as arquivo:
        for pacote, versao in pacotes_instalados.items():
            nome_base = pacote.split("==")[0]

            if versao:
                arquivo.write(
                    f"{nome_base}=={versao}\n"
                )
            else:
                arquivo.write(
                    f"{nome_base}\n"
                )

    print(
        f"[OK] Arquivo '{caminho_saida}' "
        "gerado com sucesso."
    )


def main():
    pacotes_instalados = (
        verificar_e_instalar_dependencias()
    )

    if not pacotes_instalados:
        print()
        print(
            "[ERRO] Nenhuma dependência foi instalada."
        )
        sys.exit(1)

    gerar_requirements(pacotes_instalados)

    print()
    print("=" * 60)
    print(" Processo concluído!")
    print("=" * 60)


if __name__ == "__main__":
    main()