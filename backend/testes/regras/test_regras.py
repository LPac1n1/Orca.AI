"""Perfis de regras: padrão, camadas, origem, versão, erros e travas (docs/02 §4, docs/05)."""

import re
import textwrap
from pathlib import Path

import pytest

from orca.calculo import ComparacaoMedia
from orca.regras import ErroRegras, camada_padrao, ler_camada, resolver

RAIZ = Path(__file__).resolve().parents[3]
PADRAO = camada_padrao()


def camada(texto: str, origem: str = "teste"):
    return ler_camada(textwrap.dedent(texto), origem)


def osc(corpo: str, nome: str = "OSC Exemplo", nivel: str = "osc", versao: int = 1):
    cabecalho = f"perfil: {nome}\ncamada: {nivel}\nversao: {versao}\n"
    return camada(cabecalho + textwrap.dedent(corpo))


def erro_de(*camadas) -> str:
    with pytest.raises(ErroRegras) as e:
        resolver([PADRAO, *camadas])
    return str(e.value)


# --- Perfil padrão -----------------------------------------------------------


def test_padrao_resolve_e_tem_valores_das_decisoes():
    p = resolver([PADRAO])
    r = p.regras
    assert r.fontes.fontes_por_cotacao == 3  # D-10
    assert r.fontes.validade_dias == 180  # D-12
    assert r.calculo.base_preco_final == "B"  # D-20
    assert r.calculo.comparacao_media is ComparacaoMedia.EXATA  # P-02
    assert r.otimizacao.margem_quantidade.min_percentual == -20  # D-32
    assert r.mao_de_obra.idade_maxima_vaga_dias is None  # D-47
    assert r.automacao.aprovacao_final == "manual"
    assert re.fullmatch(r"[0-9a-f]{64}", p.impressao)
    assert [c.nome for c in p.cadeia] == ["padrao-sistema"]


def test_impressao_e_deterministica():
    assert resolver([PADRAO]).impressao == resolver([camada_padrao()]).impressao


def test_documentacao_mostra_o_mesmo_perfil_padrao():
    """O bloco YAML de docs/05 §1 precisa ser idêntico ao arquivo usado pelo sistema."""
    doc = (RAIZ / "docs" / "05-regras-padrao.md").read_text(encoding="utf-8")
    bloco = re.search(r"```yaml\n(perfil: padrao-sistema\n.*?)```", doc, re.S).group(1)
    arquivo = (RAIZ / "backend" / "orca" / "regras" / "padrao-sistema.yaml").read_text(encoding="utf-8")
    assert bloco.strip() == arquivo.strip()


def test_catalogos_citados_no_perfil_existem():
    r = resolver([PADRAO]).regras
    assert (RAIZ / r.produto.atributos_criticos).is_file()
    assert (RAIZ / r.mao_de_obra.tabela_jornadas).is_file()


# --- Soma das camadas e origem de cada regra ---------------------------------


def test_camada_muda_so_o_que_declara_e_registra_a_origem():
    c = osc(
        """
        fontes:
          validade_dias: 90
          marketplace:
            permitido: false
        """,
        nome="Secretaria X",
        nivel="secretaria",
    )
    p = resolver([PADRAO, c])
    assert p.regras.fontes.validade_dias == 90
    assert p.regras.fontes.marketplace.permitido is False
    assert p.regras.fontes.marketplace.cnpj_considerado == "vendedor"  # mantido do padrão
    assert p.origem_de("fontes.validade_dias") == "Secretaria X"
    assert p.origem_de("fontes.fontes_por_cotacao") == "padrao-sistema"
    assert p.origem_de("fontes.marketplace") == "Secretaria X + padrao-sistema"
    assert [c.nivel for c in p.cadeia] == ["sistema", "secretaria"]


def test_varias_camadas_a_ultima_vence():
    a = osc("fontes:\n  validade_dias: 120\n", nome="OSC")
    b = osc("fontes:\n  validade_dias: 60\n", nome="Projeto Y", nivel="projeto")
    p = resolver([PADRAO, a, b])
    assert p.regras.fontes.validade_dias == 60
    assert p.origem_de("fontes.validade_dias") == "Projeto Y"


def test_lista_substitui_em_vez_de_somar():
    c = osc("mao_de_obra:\n  plataformas: [catho]\n")
    assert resolver([PADRAO, c]).regras.mao_de_obra.plataformas == ["catho"]


def test_grupo_vazio_limpa_e_grupo_com_chaves_soma():
    com_limite = osc('teto:\n  limites_por_orcamento: {"Mão de obra": {max_percentual: 70}}\n')
    p = resolver([PADRAO, com_limite])
    assert p.regras.teto.limites_por_orcamento["Mão de obra"].max_percentual == 70
    assert p.origem_de("teto.limites_por_orcamento.Mão de obra.max_percentual") == "OSC Exemplo"
    limpa = osc("teto:\n  limites_por_orcamento: {}\n", nome="Projeto", nivel="projeto")
    assert resolver([PADRAO, com_limite, limpa]).regras.teto.limites_por_orcamento == {}


def test_impressao_muda_com_o_valor_e_nao_com_a_ordem_das_chaves():
    base = resolver([PADRAO]).impressao
    c1 = osc("fontes:\n  validade_dias: 90\n  aviso_vencimento_dias: 10\n")
    c2 = osc("fontes:\n  aviso_vencimento_dias: 10\n  validade_dias: 90\n")
    assert resolver([PADRAO, c1]).impressao == resolver([PADRAO, c2]).impressao != base


def test_camada_ida_e_volta_em_yaml():
    c = osc("fontes:\n  validade_dias: 90\n")
    assert ler_camada(c.para_yaml()).impressao == c.impressao


def test_regra_b_ou_a_por_orcamento():
    c = osc("calculo:\n  base_preco_final: A\n", nome="Orçamento Alimentação", nivel="orcamento")
    assert resolver([PADRAO, c]).regras.calculo.base_preco_final == "A"


# --- Erros em português, com a camada responsável ----------------------------


def test_chave_desconhecida_aponta_a_camada():
    msg = erro_de(osc("fontes:\n  validade_dia: 90\n", nome="Secretaria X", nivel="secretaria"))
    assert "fontes.validade_dia: chave desconhecida (camada 'Secretaria X')" in msg


def test_valor_fora_das_opcoes_mostra_as_opcoes():
    msg = erro_de(osc("calculo:\n  base_preco_final: C\n"))
    assert "calculo.base_preco_final: valor 'C' não permitido" in msg
    assert "use: 'A' ou 'B'" in msg


def test_tipo_errado():
    assert "deve ser um número inteiro" in erro_de(osc('fontes:\n  validade_dias: "90"\n'))
    assert "deve ser true ou false" in erro_de(osc("fontes:\n  cnpjs_distintos_na_cotacao: 1\n"))


def test_decimal_e_recusado_com_a_linha():
    with pytest.raises(ErroRegras) as e:
        osc("otimizacao:\n  margem_quantidade: {min_percentual: -0.2, max_percentual: 20}\n")
    assert "linha 5" in str(e.value) and "decimal" in str(e.value)


@pytest.mark.parametrize(
    ("corpo", "trecho"),
    [
        ("automacao:\n  promover_amarelo_para_verde: automatico\n", "automacao.promover_amarelo_para_verde: precisa ser manual"),
        ("automacao:\n  aprovacao_final: com_aprovacao\n", "automacao.aprovacao_final: precisa ser manual"),
        ("automacao:\n  perfil_do_edital: automatico\n", "automacao.perfil_do_edital: precisa ser manual"),
        ("automacao:\n  resolver_item_acima_da_media: automatico\n", "não pode ser automático"),
        ("evidencia:\n  por_fonte: [png, html]\n", "o PDF da página é obrigatório"),
        ("evidencia:\n  cabecalho_pdf: [url]\n", "precisa ter data_hora"),
        ("calculo:\n  misturar_lojas_no_final: true\n", "calculo.misturar_lojas_no_final: valor True não permitido"),
    ],
)
def test_travas_dos_principios(corpo, trecho):
    msg = erro_de(osc(corpo, nome="Camada Teste"))
    assert trecho in msg
    assert "Camada Teste" in msg


@pytest.mark.parametrize(
    ("corpo", "trecho"),
    [
        ("fontes:\n  aviso_vencimento_dias: 180\n", "aviso de vencimento precisa ser menor"),
        ("otimizacao:\n  margem_horas: {min_percentual: 10, max_percentual: 20}\n", "menor ou igual a 0"),
        ('teto:\n  limites_por_orcamento: {"X": {max_percentual: 150}}\n', "menor ou igual a 100"),
        ('teto:\n  limites_por_orcamento: {"X": {min_percentual: 60, max_percentual: 50}}\n', "mínimo não pode ser maior"),
        ('teto:\n  limites_por_orcamento: {"X": {}}\n', "informe ao menos um limite"),
        ("mao_de_obra:\n  idade_maxima_vaga_dias: 0\n", "maior ou igual a 1"),
        ("mao_de_obra:\n  sequencia_arredondamento: [valor_hora, media, valor_mensal]\n", "só a sequência"),
        ("mao_de_obra:\n  plataformas: [catho, catho]\n", "valores repetidos"),
        ('preco_referencia:\n  cep: "123"\n', "use \"do_projeto\" ou um CEP"),
    ],
)
def test_valores_incoerentes(corpo, trecho):
    assert trecho in erro_de(osc(corpo))


def test_valores_validos_aceitos():
    c = osc(
        """
        preco_referencia:
          cep: "03977-015"
        mao_de_obra:
          idade_maxima_vaga_dias: 60
        teto:
          limites_por_orcamento: {"Mão de obra": {min_percentual: 10, max_percentual: 70}}
        """
    )
    r = resolver([PADRAO, c]).regras
    assert r.preco_referencia.cep == "03977-015"
    assert r.mao_de_obra.idade_maxima_vaga_dias == 60


# --- Ordem e cabeçalho das camadas -------------------------------------------


def test_ordem_das_camadas():
    sec = osc("fontes:\n  validade_dias: 90\n", nivel="secretaria", nome="Sec")
    proj = osc("fontes:\n  validade_dias: 60\n", nivel="projeto", nome="Proj")
    with pytest.raises(ErroRegras, match="fora de ordem"):
        resolver([PADRAO, proj, sec])
    with pytest.raises(ErroRegras, match="fora de ordem"):
        resolver([PADRAO, sec, sec])
    with pytest.raises(ErroRegras, match="primeira camada deve ser a do sistema"):
        resolver([sec])
    with pytest.raises(ErroRegras, match="ao menos a camada do sistema"):
        resolver([])


@pytest.mark.parametrize(
    ("texto", "trecho"),
    [
        ("camada: osc\nversao: 1\n", "falta o nome do perfil"),
        ("perfil: X\ncamada: prefeitura\nversao: 1\n", "'camada' deve ser uma destas"),
        ("perfil: X\ncamada: osc\nversao: 0\n", "'versao' deve ser um número inteiro"),
        ("perfil: X\ncamada: osc\n", "'versao' deve ser um número inteiro"),
        ("perfil: X\ncamada: osc\nversao: 1\nfontes: 3\n", "'fontes' deve ser um grupo de regras"),
        ("- a\n- b\n", "precisa ser um grupo de chaves"),
        ("perfil: [\n", "não é um YAML válido"),
    ],
)
def test_cabecalho_invalido(texto, trecho):
    with pytest.raises(ErroRegras) as e:
        ler_camada(texto, "arquivo.yaml")
    assert trecho in str(e.value)
    assert "arquivo.yaml" in str(e.value)
