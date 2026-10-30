import importlib.metadata
import subprocess
import sys


# ============================================
# Dependências necessárias para o projeto
# ============================================

# PySide6: interface gráfica do módulo de Validação do Modelo Computacional
#          (padrão visual Win11/Fluent, adotado do projeto de referência).
# openpyxl: geração da planilha Excel de resultados da validação.
DEPENDENCIAS_NECESSARIAS = [
    "dss-python",
    "matplotlib",
    "pulp",
    "PySide6",
    "openpyxl",
]


def obter_versao_instalada(pacote: str):
    """
    Retorna a versão instalada do pacote.
    Retorna None quando o pacote não está instalado.
    """
    try:
        return importlib.metadata.version(pacote)
    except importlib.metadata.PackageNotFoundError:
        return None


def instalar_pacote(pacote: str):
    """
    Instala um pacote utilizando o pip do ambiente virtual ativo.
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
            if versao:
                arquivo.write(
                    f"{pacote}=={versao}\n"
                )
            else:
                arquivo.write(
                    f"{pacote}\n"
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