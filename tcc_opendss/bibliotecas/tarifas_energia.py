__author__ = 'Pedro Henrique Sousa Pinheiro'
"""Catálogo de tarifas de energia elétrica (Grupo A), baseado na tabela
oficial da CELESC (Resolução Homologatória ANEEL nº 3.602, de 18/08/2026,
vigência 22/08/2026 a 21/08/2027), fornecida pelo usuário nesta sessão.

TRANSPARÊNCIA TÉCNICA:
    - Estes valores são de UMA distribuidora específica (CELESC-SC) e de
      UM período de vigência específico. Para uso em projeto real, o
      usuário DEVE substituir pelos valores da distribuidora e período
      de vigência aplicáveis ao seu caso. A interface (otimizacao_ui.py)
      permite edição manual dos valores de energia ponta/fora ponta -
      este catálogo serve apenas como ponto de partida/referência.
    - Valores exibidos são SEM TRIBUTOS (conforme fonte). Para tarifa
      final "com tributos", a distribuidora informa a fórmula:
      Tarifa final = Tarifa homologada / [(100-PIS-COFINS)/100] /
      [(100-ICMS)/100]. Esta conversão NÃO é aplicada automaticamente
      aqui - os valores usados na simulação são os digitados pelo
      usuário no formulário (que pode digitá-los já com tributos, se
      preferir mais realismo de custo final).
    - A modalidade "Branca" (Grupo B) não está incluída aqui, pois não é
      aplicável a unidades consumidoras do Grupo A (tensão >= 2,3 kV),
      público-alvo típico de projetos de BESS em média/alta tensão.
"""

from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional


@dataclass
class TarifaEnergia:
    nome: str
    subgrupo: str
    modalidade: str  # "Azul" ou "Verde"
    tarifa_ponta_kwh: float       # R$/kWh
    tarifa_fora_ponta_kwh: float  # R$/kWh
    demanda_ponta_kw: float = 0.0        # R$/kW (uso apenas na estimativa auxiliar de demanda)
    demanda_fora_ponta_kw: float = 0.0   # R$/kW


# Valores de referência: CELESC, Resolução Homologatória ANEEL nº 3.602/2026
# (vigência 22/08/2026 a 21/08/2027), tarifas SEM TRIBUTOS.
CATALOGO_TARIFAS_PADRAO: Dict[str, TarifaEnergia] = {
    "A2_Azul": TarifaEnergia("A2 - Horária Azul", "A2", "Azul", 0.63006, 0.43203, 22.35, 13.99),
    "A3_Azul": TarifaEnergia("A3 - Horária Azul", "A3", "Azul", 0.63438, 0.43635, 29.88, 16.36),
    "A3a_Azul": TarifaEnergia("A3a - Horária Azul", "A3a", "Azul", 0.69830, 0.50027, 41.83, 20.27),
    "A4_Azul": TarifaEnergia("A4 - Horária Azul", "A4", "Azul", 0.69830, 0.50027, 41.83, 20.27),
    "A3a_Verde": TarifaEnergia("A3a - Horária Verde", "A3a", "Verde", 1.55304, 0.44558, 0.0, 20.27),
    "A4_Verde": TarifaEnergia("A4 - Horária Verde", "A4", "Verde", 1.71635, 0.50027, 0.0, 20.27),
}


def listar_opcoes_tarifa() -> List[Tuple[str, str]]:
    """Retorna lista de tuplas (chave, rótulo) para uso em Combobox."""
    return [(chave, tarifa.nome) for chave, tarifa in CATALOGO_TARIFAS_PADRAO.items()]


def obter_tarifa(chave: str) -> Optional[TarifaEnergia]:
    return CATALOGO_TARIFAS_PADRAO.get(chave)