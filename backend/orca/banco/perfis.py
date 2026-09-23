"""Perfis de regras no banco: versões imutáveis e a cadeia de cada projeto e orçamento."""

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from orca.banco.tabelas import Orcamento, PerfilRegras, Projeto
from orca.regras import Camada, ErroRegras, PerfilResolvido, camada_padrao, ler_camada, resolver


def registrar_camada(sessao: Session, camada: Camada, organizacao_id: str | None = None) -> PerfilRegras:
    """Grava uma versão de camada. Se já existir igual, devolve a existente.

    A mesma camada (nome e versão) com conteúdo diferente é recusada: mudou o conteúdo,
    aumente a versão. A camada do sistema é global; as demais pertencem a uma organização.
    """
    if (camada.nivel == "sistema") != (organizacao_id is None):
        raise ErroRegras(["a camada do sistema não tem organização; as demais precisam ter"])
    filtro_org = PerfilRegras.organizacao_id.is_(None) if organizacao_id is None else (
        PerfilRegras.organizacao_id == organizacao_id
    )
    existente = sessao.scalars(
        select(PerfilRegras).where(filtro_org, PerfilRegras.nome == camada.nome, PerfilRegras.versao == camada.versao)
    ).first()
    if existente is not None:
        if existente.impressao != camada.impressao:
            raise ErroRegras(
                [f"a camada '{camada.nome}' versão {camada.versao} já existe com outro conteúdo; aumente a versão"]
            )
        return existente
    registro = PerfilRegras(
        organizacao_id=organizacao_id,
        nome=camada.nome,
        nivel=camada.nivel,
        versao=camada.versao,
        impressao=camada.impressao,
        conteudo_yaml=camada.para_yaml(),
    )
    sessao.add(registro)
    return registro


def camada_de(registro: PerfilRegras) -> Camada:
    """Lê a camada gravada e confere que o conteúdo é o mesmo que foi registrado."""
    camada = ler_camada(registro.conteudo_yaml, f"perfil_regras {registro.nome} v{registro.versao}")
    if camada.impressao != registro.impressao:
        raise ErroRegras([f"o conteúdo gravado da camada '{registro.nome}' v{registro.versao} não confere"])
    return camada


def definir_camadas_do_projeto(
    sessao: Session, projeto: Projeto, camadas: Sequence[Camada] = (), com_padrao: bool = True
) -> PerfilResolvido:
    """Grava as camadas (padrão do sistema + as informadas) e liga o projeto a essas versões.

    A cadeia é validada antes de ser gravada. Camadas de orçamento não entram aqui.
    """
    cadeia = ([camada_padrao()] if com_padrao else []) + list(camadas)
    if any(c.nivel == "orcamento" for c in cadeia):
        raise ErroRegras(["camadas de orçamento são ligadas ao orçamento, não ao projeto"])
    perfil = resolver(cadeia)
    organizacao_id = projeto.organizacao_id or (projeto.organizacao.id if projeto.organizacao else None)
    registros = [
        registrar_camada(sessao, c, None if c.nivel == "sistema" else organizacao_id) for c in cadeia
    ]
    sessao.flush()
    projeto.camadas_regras = [r.id for r in registros]
    return perfil


def definir_camada_do_orcamento(sessao: Session, orcamento: Orcamento, camada: Camada | None) -> PerfilResolvido:
    """Liga (ou remove, com None) a camada própria do orçamento, validando a cadeia completa."""
    if camada is not None and camada.nivel != "orcamento":
        raise ErroRegras([f"a camada do orçamento precisa ter nível 'orcamento', não '{camada.nivel}'"])
    projeto = orcamento.projeto
    cadeia = _camadas_do_projeto(sessao, projeto) + ([camada] if camada else [])
    perfil = resolver(cadeia)
    if camada is None:
        orcamento.camada_regras_id = None
    else:
        registro = registrar_camada(sessao, camada, projeto.organizacao_id)
        sessao.flush()
        orcamento.camada_regras_id = registro.id
    return perfil


def _camadas_do_projeto(sessao: Session, projeto: Projeto) -> list[Camada]:
    if not projeto.camadas_regras:
        raise ErroRegras([f"o projeto '{projeto.nome}' ainda não tem regras definidas"])
    camadas = []
    for identificador in projeto.camadas_regras:
        registro = sessao.get(PerfilRegras, identificador)
        if registro is None:
            raise ErroRegras([f"camada de regras {identificador} não encontrada"])
        camadas.append(camada_de(registro))
    return camadas


def perfil_do_projeto(sessao: Session, projeto: Projeto) -> PerfilResolvido:
    return resolver(_camadas_do_projeto(sessao, projeto))


def perfil_do_orcamento(sessao: Session, orcamento: Orcamento) -> PerfilResolvido:
    """Regras que valem para o orçamento: as do projeto mais a camada própria, se houver."""
    camadas = _camadas_do_projeto(sessao, orcamento.projeto)
    if orcamento.camada_regras_id:
        camadas.append(camada_de(sessao.get(PerfilRegras, orcamento.camada_regras_id)))
    return resolver(camadas)
