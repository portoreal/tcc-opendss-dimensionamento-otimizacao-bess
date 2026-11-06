__author__ = 'Pedro Henrique Sousa Pinheiro'
"""Tarifas de energia elétrica do Grupo A a partir da tabela oficial da
CELESC (Resolução Homologatória ANEEL nº 3.602, de 18/08/2026, vigência de
22/08/2026 a 21/08/2027), fornecida pelo usuário nesta sessão.

TRANSPARÊNCIA TÉCNICA:
    - Os valores são de UMA distribuidora (CELESC-SC) e de UM período de
      vigência. Em projeto real, o usuário DEVE substituí-los pelos da
      distribuidora e do ciclo que se aplicam ao seu caso. A interface
      (otimizacao_ui.py) aceita edição manual das tarifas de energia de
      ponta e de fora ponta; este catálogo é só ponto de partida.
    - Os valores são SEM TRIBUTOS, como na fonte. Para a tarifa final com
      tributos, a distribuidora informa:
      Tarifa final = Tarifa homologada / [(100-PIS-COFINS)/100] /
      [(100-ICMS)/100]. Essa conversão não é aplicada aqui de forma
      automática: a simulação usa exatamente o que o usuário digitar no
      formulário — que pode ser o valor já tributado, se quiser realismo
      de custo final.
    - A modalidade Branca (Grupo B) não entra: ela não se aplica a
      unidades do Grupo A (tensão >= 2,3 kV), que é justamente o
      público-alvo de BESS em média/alta tensão.
"""

from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional


@dataclass
class TarifaEnergia:
    nome: str
    subgrupo: str
    modalidade: str  # "Azul" ou "Verde"
    # Energia: R$ por kWh consumido, separado em posto ponta (3 h diárias,
    # tipicamente 18h-21h) e fora ponta (as outras 21 h).
    tarifa_ponta_kwh: float
    tarifa_fora_ponta_kwh: float
    # Demanda: R$ por kW de demanda faturável. Na modalidade Azul há duas
    # parcelas (ponta e fora ponta); na Verde só a de fora ponta, porque a
    # ponta é cobrada apenas por energia. Os valores aqui alimentam apenas
    # a estimativa auxiliar de demanda — não entram na economia do BESS.
    demanda_ponta_kw: float = 0.0
    demanda_fora_ponta_kw: float = 0.0


# Valores de referência: CELESC, Resolução Homologatória ANEEL nº 3.602/2026
# (vigência 22/08/2026 a 21/08/2027), tarifas SEM TRIBUTOS.
#
# A chave do dicionário segue o padrão "<subgrupo>_<modalidade>" e é o que
# o Combobox devolve ao ser selecionado. Duas leituras úteis para comparar
# as linhas: a tarifa de ponta da Verde é cerca de três vezes a da Azul (o
# consumidor paga por isso em kWh, não em demanda), e A3a e A4 têm valores
# idênticos por coincidência tarifária da concessionária — não é erro de
# digitação.
CATALOGO_TARIFAS_PADRAO: Dict[str, TarifaEnergia] = {
    "A2_Azul": TarifaEnergia("A2 - Horária Azul", "A2", "Azul", 0.63006, 0.43203, 22.35, 13.99),
    "A3_Azul": TarifaEnergia("A3 - Horária Azul", "A3", "Azul", 0.63438, 0.43635, 29.88, 16.36),
    "A3a_Azul": TarifaEnergia("A3a - Horária Azul", "A3a", "Azul", 0.69830, 0.50027, 41.83, 20.27),
    "A4_Azul": TarifaEnergia("A4 - Horária Azul", "A4", "Azul", 0.69830, 0.50027, 41.83, 20.27),
    "A3a_Verde": TarifaEnergia("A3a - Horária Verde", "A3a", "Verde", 1.55304, 0.44558, 0.0, 20.27),
    "A4_Verde": TarifaEnergia("A4 - Horária Verde", "A4", "Verde", 1.71635, 0.50027, 0.0, 20.27),
}


def listar_opcoes_tarifa() -> List[Tuple[str, str]]:
    """Devolve [(chave, rótulo), ...] para alimentar um Combobox.

    A chave é o identificador curto usado no código; o rótulo é o texto que
    aparece na tela. Manter os dois evita que o código passe a depender de
    texto de interface.
    """
    return [(chave, tarifa.nome) for chave, tarifa in CATALOGO_TARIFAS_PADRAO.items()]


def obter_tarifa(chave: str) -> Optional[TarifaEnergia]:
    # Retorna None quando a chave não existe (combobox ainda não preenchido,
    # por exemplo); quem chama decide o que fazer, em vez de estourar exceção.
    return CATALOGO_TARIFAS_PADRAO.get(chave)