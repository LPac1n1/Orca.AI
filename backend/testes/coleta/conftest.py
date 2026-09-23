from datetime import date

import pytest

from orca.banco import Cargo, Item, Lote, Orcamento, Organizacao, Projeto, abrir_banco, definir_camadas_do_projeto, sessao_como
from orca.evidencias import ArmazemArquivos

from apoio_coleta import USUARIO


@pytest.fixture
def fabrica(tmp_path):
    return abrir_banco(tmp_path / "orca.sqlite")


@pytest.fixture
def armazem(tmp_path):
    return ArmazemArquivos(tmp_path / "dados")


@pytest.fixture
def ids(fabrica):
    """Projeto (entrega em 30/06/2027) com um item de papelaria e um cargo."""
    with sessao_como(fabrica, USUARIO) as s:
        org = Organizacao(nome="OSC Exemplo", cnpj="03.645.949/0001-37")
        projeto = Projeto(
            organizacao=org, nome="Projeto Exemplo", teto_centavos=15_000_000, duracao_meses=12,
            data_entrega=date(2027, 6, 30),
        )
        s.add(projeto)
        definir_camadas_do_projeto(s, projeto)
        materiais = Orcamento(projeto=projeto, nome="Material pedagógico", tipo="materiais")
        pessoal = Orcamento(projeto=projeto, nome="Recursos humanos", tipo="mao_de_obra")
        item = Item(
            lote=Lote(orcamento=materiais, nome="Papelaria"), descricao="Papel sulfite A4 75g 500 folhas",
            marca="Chamex", qtd_planejada=20, mes_inicio=1, mes_fim=1,
        )
        cargo = Cargo(
            orcamento=pessoal, nome="Educador social", regime="recibo", horas_planejadas_centesimos=8000,
            mes_inicio=1, mes_fim=12,
        )
        s.add_all([item, cargo])
        s.flush()
        return {"projeto": projeto.id, "item": item.id, "cargo": cargo.id}
