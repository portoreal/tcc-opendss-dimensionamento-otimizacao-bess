__author__ = 'Pedro Henrique Sousa Pinheiro'
"""Modelo de dados da rede elétrica, sem nada de interface.

Este módulo guarda o que a rede É: barras, ramos, derivações e as curvas
XY auxiliares. Nenhuma linha daqui desenha, clica ou abre janela — o editor
gráfico, o exportador e o otimizador leem e escrevem nesta estrutura. Essa
separação é o que permite rodar a simulação e a otimização sem carregar a
interface junto.

O vocabulário é o do OpenDSS. Barra é o nó elétrico, onde a tensão é medida.
Ramo liga duas barras (linha, transformador, chave). Derivação é o que se
pendura em uma barra só (carga, gerador, capacitor, PVSystem, Storage,
reator) ou o que não se pendura em barra nenhuma (InvControl). Tudo é
guardado em dicionários com o nome do elemento como chave, porque no OpenDSS
o nome é o identificador.
"""
import json
import re
from dataclasses import dataclass, field, asdict
from typing import Dict, Any, Optional, Iterable, List


def gerar_nome_unico(nome_base: str, nomes_existentes: Iterable[str]) -> str:
    """Devolve um nome que ainda não esteja em 'nomes_existentes'.

    Nome livre volta como veio. Nome já usado ganha um sufixo numérico igual
    ao maior sufixo já ocupado mais um — assim "linha" vira "linha1", e se
    "linha1" também existir vira "linha2", sem reaproveitar buraco deixado no
    meio da sequência.

    Exemplos:
        "linha" (livre)                          -> "linha"
        "linha" (já existe "linha")               -> "linha1"
        "linha" (já existem "linha","linha1"..4)  -> "linha5"
    """
    nome_base = nome_base.strip()
    nomes_existentes = set(nomes_existentes)

    if nome_base not in nomes_existentes:
        return nome_base

    padrao = re.compile(rf'^{re.escape(nome_base)}(\d*)$')
    maior_sufixo = 0

    for nome in nomes_existentes:
        m = padrao.match(nome)
        if m:
            sufixo = m.group(1)
            numero = int(sufixo) if sufixo else 0
            maior_sufixo = max(maior_sufixo, numero)

    return f"{nome_base}{maior_sufixo + 1}"


@dataclass
class Barra:
    nome: str
    kv_base: float = 13.8
    # Onde o usuário deixou esta barra no diagrama, em coordenadas de
    # cena do editor: [x, y]. Vazio (None) significa "nunca foi movida" e
    # devolve o desenho ao layout automático. O par existe para que o
    # arranjo montado à mão sobreviva ao fechamento do projeto — antes,
    # a posição vivia só na memória do editor e se perdia a cada
    # abertura.
    posicao: Optional[List[float]] = None
    # Rótulo "Barra / Tensão" visível no diagrama. Falso esconde o texto
    # sem apagar a barra, útil em redes densas.
    rotulo_visivel: bool = True
    # Desvio [dx, dy] do rótulo em relação ao centro da barra. O padrão
    # do desenho põe o texto logo acima da elipse; este campo guarda a
    # correção que o usuário impôs arrastando o próprio texto.
    rotulo_posicao: Optional[List[float]] = None


@dataclass
class ElementoRamo:
    """Elemento que liga duas barras: Line, Transformer ou Switch.

    bus1 e bus2 são os terminais, e a ordem importa — o exportador usa essa
    ordem como terminal 1 e terminal 2 no comando do OpenDSS.
    """
    tipo: str
    nome: str
    bus1: str
    bus2: str
    parametros: Dict[str, Any] = field(default_factory=dict)
    # Rótulo do ramo (tipo e nome no meio da linha) visível. Nasceu junto
    # com o clique que alterna o rótulo de cada elemento; antes disso, só
    # o botão global governava os rótulos dos ramos.
    rotulo_visivel: bool = True
    # Desvio [dx, dy] do rótulo em relação ao ponto onde ele nasceria
    # sozinho (o meio da linha, recuado na perpendicular). None significa
    # "automático". Guardar o desvio, e não a coordenada absoluta, é o
    # que mantém o texto colado ao ramo quando a topologia muda e o
    # desenho se refaz.
    rotulo_posicao: Optional[List[float]] = None


@dataclass
class ElementoDerivacao:
    """Elemento pendurado em uma barra — ou em nenhuma.

    Três casos convivem nesta mesma estrutura:

    - Ligado a UMA barra: Load, Generator, Capacitor, PVSystem, Storage,
      Reactor e a Vsource/Fonte.
    - Sem conexão física com barra alguma: InvControl, que referencia o que
      controla pelo DERList dentro de parametros. Para ele, bus1 fica None e
      ligar a uma barra seria erro de modelagem.
    - Ancorado numa barra só para efeito de desenho: EnergyMeter. O comando
      do OpenDSS aponta para o ELEMENTO medido, guardado em
      parametros['element']. A bus1 aqui não é conexão elétrica: é onde o
      ícone aparece no editor e por onde a exclusão em cascata o encontra.

    O campo 'grupo' diz a que conjunto este elemento pertence. Um "Sistema
    BESS", por exemplo, é um Storage mais um InvControl mais, quando houver,
    um Capacitor ou Reator — elementos que não fazem sentido separados e por
    isso são excluídos juntos. Elemento criado sozinho tem grupo=None.
    """
    tipo: str
    nome: str
    bus1: Optional[str] = None
    parametros: Dict[str, Any] = field(default_factory=dict)
    grupo: Optional[str] = None
    # Mesmo contrato da Barra.posicao: coordenada de cena do ajuste
    # manual, ou None para o leque automático ao redor da barra.
    posicao: Optional[List[float]] = None
    # Rótulo do elemento (tipo, nome e o ícone de curva) visível.
    rotulo_visivel: bool = True
    # Mesmo contrato do ElementoRamo.rotulo_posicao: desvio [dx, dy] em
    # relação ao centro da caixa, onde o rótulo nasce.
    rotulo_posicao: Optional[List[float]] = None


@dataclass
class CurvaXY:
    """Curva X-Y do OpenDSS (New XYCurve), hoje usada pelas leis Volt-Var e
    Volt-Watt do InvControl.

    Guarda duas listas de mesmo tamanho: xarray é a entrada e yarray a saída
    pedida ao inversor.
    """
    nome: str
    npts: int
    xarray: List[float] = field(default_factory=list)
    yarray: List[float] = field(default_factory=list)


class RedeEletrica:
    """O grafo completo da rede, mais as curvas XY que os elementos citam.

    Quatro dicionários, todos indexados pelo nome do elemento: barras, ramos,
    derivacoes e curvas_xy. Não há checagem de consistência global aqui — a
    validação de topologia acontece antes de exportar.
    """

    def __init__(self):
        self.barras: Dict[str, Barra] = {}
        self.ramos: Dict[str, ElementoRamo] = {}
        self.derivacoes: Dict[str, ElementoDerivacao] = {}
        self.curvas_xy: Dict[str, CurvaXY] = {}

    # ---------------------------- BARRAS ---------------------------- #
    def adicionar_barra(self, nome: str, kv_base: float = 13.8) -> str:
        """Cria a barra com essa tensão de base e devolve o nome que ficou.

        Nome repetido não gera exceção: a barra é renomeada e o autor da
        chamada precisa usar o nome devolvido, não o que pediu. Use o retorno.
        """
        nome_final = gerar_nome_unico(nome, self.barras.keys())
        self.barras[nome_final] = Barra(nome_final, kv_base)
        return nome_final

    def remover_barra(self, nome: str):
        """Remove a barra levando junto tudo que dependia dela.

        Some a barra, somem os ramos que a tocavam e somem as derivações
        nela penduradas. A remoção de grupo torna a cascata mais ampla: se um
        dos elementos removidos fazia parte de um conjunto, o conjunto inteiro
        vai embora, inclusive as partes que não tocavam nesta barra. O caso
        concreto é o InvControl, que não tem bus1 próprio — apagada a barra do
        Storage, ele ficaria vivo apontando, via DERList, para um elemento que
        não existe mais, e o erro só apareceria no motor.
        """
        self.barras.pop(nome, None)

        for chave in [k for k, r in self.ramos.items() if nome in (r.bus1, r.bus2)]:
            self.ramos.pop(chave, None)

        grupos_a_remover = {
            d.grupo for d in self.derivacoes.values()
            if d.bus1 == nome and d.grupo
        }
        for grupo in grupos_a_remover:
            self.remover_grupo(grupo)

        for chave in [k for k, d in self.derivacoes.items() if d.bus1 == nome]:
            self.derivacoes.pop(chave, None)

        # O ramo que acabou de sair pode ser justamente o que um medidor
        # monitorava. Quem mede um elemento que sumiu não tem mais o que
        # medir, então o medidor vai junto.
        self.limpar_medidores_orfaos()
    def renomear_barra(self, nome_antigo: str, nome_novo: str) -> str:
        """Renomeia a barra e reescreve as referências a ela nos ramos e nas
        derivações, devolvendo o nome que ficou.

        O nome é a ligação entre os elementos neste modelo, então trocá-lo sem
        percorrer quem o cita romperia a topologia. Colisão com outra barra
        não gera exceção: o novo nome é ajustado e o retorno traz o valor
        efetivo.
        """

        if nome_antigo not in self.barras:
            raise ValueError(f"Barra '{nome_antigo}' não encontrada.")

        nome_final = nome_novo.strip()
        if nome_final != nome_antigo:
            outros_nomes = [n for n in self.barras if n != nome_antigo]
            nome_final = gerar_nome_unico(nome_final, outros_nomes)

        barra = self.barras.pop(nome_antigo)
        barra.nome = nome_final
        self.barras[nome_final] = barra

        for ramo in self.ramos.values():
            if ramo.bus1 == nome_antigo:
                ramo.bus1 = nome_final
            if ramo.bus2 == nome_antigo:
                ramo.bus2 = nome_final

        for der in self.derivacoes.values():
            if der.bus1 == nome_antigo:
                der.bus1 = nome_final

        return nome_final

    # ---------------------------- RAMOS ---------------------------- #
    def adicionar_ramo(self, tipo: str, nome: str, bus1: str, bus2: str,
                        parametros: Optional[Dict[str, Any]] = None) -> str:
        """Liga duas barras existentes e devolve o nome que ficou.

        As duas barras precisam existir antes, e precisam ser diferentes:
        um ramo com bus1 igual a bus2 vira um curto-circuito, não um
        equipamento. Nome repetido é renomeado em silêncio.
        """

        if bus1 not in self.barras or bus2 not in self.barras:
            raise ValueError("Ambas as barras precisam existir antes de criar o ramo.")
        if bus1 == bus2:
            raise ValueError("A barra de origem e destino devem ser diferentes.")

        nome_final = gerar_nome_unico(nome, self.ramos.keys())
        self.ramos[nome_final] = ElementoRamo(tipo, nome_final, bus1, bus2, parametros or {})
        return nome_final

    def remover_ramo(self, nome: str):
        self.ramos.pop(nome, None)

    # -------------------------- DERIVAÇÕES -------------------------- #
    def adicionar_derivacao(self, tipo: str, nome: str, bus1: Optional[str] = None,
                             parametros: Optional[Dict[str, Any]] = None,
                             grupo: Optional[str] = None) -> str:
        """Cria a derivação e devolve o nome que ficou.

        Bus1 com nome de barra inexistente é ValueError, porque elemento
        pendurado no vazio não tem leitura possível no OpenDSS. bus1=None é
        legítimo apenas para quem não se conecta a barra alguma — o caso é o
        InvControl, que referencia o controlado por DERList.
        """

        if bus1 is not None and bus1 not in self.barras:
            raise ValueError("A barra precisa existir antes de conectar o elemento.")

        nome_final = gerar_nome_unico(nome, self.derivacoes.keys())
        self.derivacoes[nome_final] = ElementoDerivacao(
            tipo, nome_final, bus1, parametros or {}, grupo)
        return nome_final

    def remover_derivacao(self, nome: str):
        self.derivacoes.pop(nome, None)

    def remover_grupo(self, nome_grupo: str):
        """Remove todas as derivações de um mesmo conjunto lógico.

        É o que permite apagar um Sistema BESS inteiro (Storage, InvControl e
        o Capacitor ou Reator associado) partindo de qualquer um de seus
        integrantes, sem deixar metade do conjunto para trás.
        """
        for chave in [k for k, d in self.derivacoes.items() if d.grupo == nome_grupo]:
            self.derivacoes.pop(chave, None)

    def obter_grupo(self, nome_grupo: str) -> Dict[str, ElementoDerivacao]:
        """Devolve as derivações que compõem um conjunto, indexadas por nome."""
        return {k: d for k, d in self.derivacoes.items() if d.grupo == nome_grupo}

    def obter_fonte(self) -> Optional[ElementoDerivacao]:
        """Devolve a Vsource da rede, ou None se não houver nenhuma.

        Não confere se existe mais de uma. Uma rede com duas fontes é erro de
        modelagem, e o exportador acusa isso ao gerar o Master.
        """
        fontes = [d for d in self.derivacoes.values() if d.tipo == "Vsource"]
        return fontes[0] if fontes else None

    # ---------------------- MEDIDOR DE ENERGIA ---------------------- #
    # O EnergyMeter não é um equipamento da rede: é a posição onde se mede.
    # No OpenDSS o comando aponta para um ELEMENTO já definido (Line.L1, por
    # exemplo) e mede o que passa por ele, não para uma barra.
    #
    # O modelo segue essa lógica: a referência real fica em
    # parametros['element'] e a bus1 da derivação serve só como âncora visual,
    # que é onde o ícone aparece no editor.
    #
    # Restrição verificada no motor real (dss-python 0.15.7): o alvo precisa
    # ser um elemento de entrega de potência (Line, Switch, Transformer,
    # Reactor, Capacitor). Pedir para medir a própria fonte é recusado com
    # "not a Power Delivery element". É por isso que a posição padrão exige ao
    # menos um ramo saindo da barra da fonte: sem ramo não há o que medir.

    def sugerir_medidor_padrao(self):
        """Posição padrão do medidor: a entrada de energia da rede.

        Na prática, a entrada é o primeiro ramo que toca a barra da fonte, na
        ordem em que os ramos foram criados — e essa ordem é estável, porque
        dicionário em Python preserva a inserção.

        O terminal segue o lado por onde o ramo encosta na fonte: se o bus1
        do ramo é a barra da fonte, terminal 1; se é o bus2, terminal 2.
        Medir o terminal errado é medir o lado do equipamento, não a
        fronteira com a concessionária.

        Sem fonte, ou com a fonte isolada (nenhum ramo nela), não existe
        posição padrão que faça sentido e o retorno é None. Quem chama deve
        recusar a criação com mensagem clara em vez de gravar uma referência
        quebrada.

        Retorna (elemento, terminal, barra_ancora) ou None.
        """
        fonte = self.obter_fonte()
        if fonte is None or not fonte.bus1:
            return None

        for ramo in self.ramos.values():
            if ramo.bus1 == fonte.bus1:
                return (f"{ramo.tipo}.{ramo.nome}", 1, fonte.bus1)
            if ramo.bus2 == fonte.bus1:
                return (f"{ramo.tipo}.{ramo.nome}", 2, fonte.bus1)
        return None

    def resolver_alvo_medidor(self, elemento: str, terminal=1) -> Optional[str]:
        """Converte a referência de um medidor ('Line.L1') na barra onde o
        ícone deve ser ancorado.

        A referência nomeia o ramo e o terminal diz qual ponta dele está sendo
        medida: terminal 1 devolve bus1, terminal 2 devolve bus2.

        Retorna None quando o ramo não existe mais ou quando o tipo não bate —
        o nome foi reaproveitado por outro equipamento, por exemplo. Quem
        chama decide o que fazer com isso: o exportador trata como erro de
        exportação, o editor como formulário inválido.
        """
        elemento = str(elemento or "").strip()
        if "." not in elemento:
            return None

        tipo, _, nome = elemento.partition(".")
        ramo = self.ramos.get(nome.strip())
        if ramo is None or ramo.tipo != tipo:
            return None

        return ramo.bus1 if int(terminal) == 1 else ramo.bus2

    def limpar_medidores_orfaos(self) -> List[str]:
        """Apaga os medidores que perderam o alvo e devolve o nome dos
        removidos.

        Chamada nas exclusões que podem deixar medidor órfão.

        De propósito, não é chamada dentro de remover_ramo nem de
        remover_derivacao. O editor edita um ramo removendo e recriando, e
        nesse intervalo o medidor fica momentaneamente órfão sendo, na
        verdade, válido. Podar ali apagaria a configuração do usuário por
        causa de um passo intermediário da edição. Quem cobre esse caso é a
        reatribuição de referências.
        """
        removidos = []
        for chave in list(self.derivacoes.keys()):
            der = self.derivacoes[chave]
            if der.tipo != "EnergyMeter":
                continue
            alvo = str(der.parametros.get("element", "") or "")
            if self.resolver_alvo_medidor(alvo, der.parametros.get("terminal", 1)) is None:
                removidos.append(chave)
                self.derivacoes.pop(chave)
        return removidos

    def reatribuir_medidores(self, elemento_antigo: str, elemento_novo: str):
        """Move os medidores de um elemento para outro.

        Serve quando o editor renomeia um ramo ou troca seu tipo — 'Line.L1'
        virando 'Switch.L1', por exemplo. Sem isso o medidor continuaria
        apontando para a referência velha, e a limpeza de órfãos o apagaria:
        a configuração do usuário se perderia num caso que deveria ser
        transparente para ele.
        """
        if elemento_antigo == elemento_novo:
            return
        for der in self.derivacoes.values():
            if (der.tipo == "EnergyMeter"
                    and str(der.parametros.get("element", "")) == elemento_antigo):
                der.parametros["element"] = elemento_novo

    # --------------------------- CURVAS XY --------------------------- #
    def adicionar_curva_xy(self, nome: str, xarray: List[float], yarray: List[float]) -> str:
        """Registra uma curva XY e devolve o nome que ficou.

        Curva com nome livre é gravada como veio. Se já existe uma curva com o
        mesmo nome e os mesmos pontos, ela é reaproveitada — sem isso, cada
        Sistema BESS novo duplicaria a mesma curva padrão. Nome igual com
        pontos diferentes é renomeado, porque duas curvas distintas não podem
        disputar o mesmo identificador no OpenDSS.
        """
        existente = self.curvas_xy.get(nome)

        if existente is None:
            self.curvas_xy[nome] = CurvaXY(nome, len(xarray), list(xarray), list(yarray))
            return nome

        if list(existente.xarray) == list(xarray) and list(existente.yarray) == list(yarray):
            return nome

        nome_final = gerar_nome_unico(nome, self.curvas_xy.keys())
        self.curvas_xy[nome_final] = CurvaXY(nome_final, len(xarray), list(xarray), list(yarray))
        return nome_final

    # --------------------------- PERSISTÊNCIA --------------------------- #
    def to_dict(self) -> dict:
        return {
            "barras": {k: asdict(v) for k, v in self.barras.items()},
            "ramos": {k: asdict(v) for k, v in self.ramos.items()},
            "derivacoes": {k: asdict(v) for k, v in self.derivacoes.items()},
            "curvas_xy": {k: asdict(v) for k, v in self.curvas_xy.items()},
        }

    def salvar_json(self, caminho: str):
        """Grava a rede inteira em `caminho`, com o layout do diagrama.

        As posições e a visibilidade de rótulos entram junto dos dados
        elétricos: quem organizou o desenho encontra o mesmo arranjo na
        próxima abertura.
        """
        with open(caminho, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)

    @classmethod
    def carregar_json(cls, caminho: str) -> "RedeEletrica":
        """Lê a rede de um rede.json e devolve o objeto pronto.

        Cada barra é filtrada nos campos conhecidos antes de virar
        dataclass. Assim um JSON com campo extra — de versão futura ou de
        edição manual — não quebra a leitura. Os campos de layout entram
        nesse filtro: rede salva antes de existir posição não traz a
        chave, o padrão do dataclass assume e o arranjo automático de
        sempre é reproduzido.
        """
        with open(caminho, "r", encoding="utf-8") as f:
            dados = json.load(f)

        rede = cls()
        for nome, b in dados.get("barras", {}).items():
            b_filtrado = {
                k: v for k, v in b.items()
                if k in ("nome", "kv_base", "posicao", "rotulo_visivel",
                         "rotulo_posicao")
            }
            rede.barras[nome] = Barra(**b_filtrado)
        for nome, r in dados.get("ramos", {}).items():
            # Mesmo filtro das barras, pelo mesmo motivo: ramo salvo
            # antes dos campos de rótulo não os traz no JSON, e os
            # padrões do dataclass devolvem o rótulo visível no lugar
            # automático.
            r_filtrado = {
                k: v for k, v in r.items()
                if k in ("tipo", "nome", "bus1", "bus2", "parametros",
                         "rotulo_visivel", "rotulo_posicao")
            }
            rede.ramos[nome] = ElementoRamo(**r_filtrado)
        for nome, d in dados.get("derivacoes", {}).items():
            # Projetos salvos antes de existirem 'grupo', 'posicao' e o
            # bus1 opcional não trazem essas chaves. Ausentes no JSON,
            # valem os padrões do dataclass e o arquivo antigo continua
            # abrindo.
            rede.derivacoes[nome] = ElementoDerivacao(**d)
        for nome, c in dados.get("curvas_xy", {}).items():
            rede.curvas_xy[nome] = CurvaXY(**c)

        return rede