import pytest

from orca.banco import Lote, Orcamento, Organizacao, Projeto, abrir_banco, definir_camadas_do_projeto, sessao_como

USUARIO = "usuario:Leonardo"


@pytest.fixture
def fabrica(tmp_path):
    return abrir_banco(tmp_path / "orca.sqlite")


@pytest.fixture
def projeto_id(fabrica):
    """Organização + projeto com regras padrão + uma rubrica de materiais com um lote."""
    with sessao_como(fabrica, USUARIO) as s:
        org = Organizacao(nome="OSC Exemplo", cnpj="03.645.949/0001-37")
        projeto = Projeto(organizacao=org, nome="Projeto Exemplo", teto_centavos=15_000_000, duracao_meses=12)
        s.add(projeto)
        definir_camadas_do_projeto(s, projeto)
        orcamento = Orcamento(projeto=projeto, nome="Material pedagógico", tipo="materiais")
        s.add(Lote(orcamento=orcamento, nome="Papelaria"))
        s.flush()
        return projeto.id
