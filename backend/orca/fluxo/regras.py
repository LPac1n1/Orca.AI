"""Regras editadas pela interface: a camada do projeto e a de cada orçamento (docs/02 §4).

Cada gravação é uma versão nova da camada (as anteriores ficam no banco, D-07). A cadeia
inteira é validada antes: travas dos princípios e valores fora do permitido são recusados.
"""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from orca.banco import Orcamento, PerfilRegras, Projeto, camada_de, definir_camada_do_orcamento, definir_camadas_do_projeto
from orca.regras import Camada, PerfilResolvido


def _camadas(sessao: Session, projeto: Projeto) -> list[Camada]:
    return [camada_de(sessao.get(PerfilRegras, i)) for i in projeto.camadas_regras or ()]


def _nova_versao(sessao: Session, organizacao_id: str, nome: str, nivel: str, conteudo: dict, descricao: str) -> Camada:
    """A próxima versão da camada `nome` (ou a última, se o conteúdo não mudou)."""
    ultima = sessao.scalars(
        select(PerfilRegras).where(PerfilRegras.organizacao_id == organizacao_id, PerfilRegras.nome == nome)
        .order_by(PerfilRegras.versao.desc())
    ).first()
    if ultima is not None:
        camada = camada_de(ultima)
        if dict(camada.conteudo) == conteudo:
            return camada
    versao = (sessao.scalar(select(func.max(PerfilRegras.versao)).where(
        PerfilRegras.organizacao_id == organizacao_id, PerfilRegras.nome == nome)) or 0) + 1
    return Camada(nome, nivel, versao, conteudo, descricao=descricao)


def regras_proprias_do_projeto(sessao: Session, projeto: Projeto) -> dict:
    atual = next((c for c in _camadas(sessao, projeto) if c.nivel == "projeto"), None)
    return dict(atual.conteudo) if atual else {}


def salvar_regras_do_projeto(sessao: Session, projeto: Projeto, conteudo: dict) -> PerfilResolvido:
    """Troca a camada do projeto (conteúdo vazio = valem só as camadas de cima)."""
    camadas = _camadas(sessao, projeto)
    atual = next((c for c in camadas if c.nivel == "projeto"), None)
    novas = [c for c in camadas if c.nivel not in ("sistema", "projeto")]
    if conteudo:
        nome = atual.nome if atual else f"projeto-{projeto.id[:12]}"
        novas.append(_nova_versao(sessao, projeto.organizacao_id, nome, "projeto", conteudo,
                                  f"Regras do projeto {projeto.nome}"))
    return definir_camadas_do_projeto(sessao, projeto, novas)


def regras_proprias_do_orcamento(sessao: Session, orcamento: Orcamento) -> dict:
    if not orcamento.camada_regras_id:
        return {}
    return dict(camada_de(sessao.get(PerfilRegras, orcamento.camada_regras_id)).conteudo)


def salvar_regras_do_orcamento(sessao: Session, orcamento: Orcamento, conteudo: dict) -> PerfilResolvido:
    """Regras só deste orçamento (ex.: regra A num e regra B noutro, T-13). Vazio = sem camada própria."""
    nova = None
    if conteudo:
        atual = camada_de(sessao.get(PerfilRegras, orcamento.camada_regras_id)) if orcamento.camada_regras_id else None
        nome = atual.nome if atual else f"orcamento-{orcamento.id[:12]}"
        nova = _nova_versao(sessao, orcamento.projeto.organizacao_id, nome, "orcamento", conteudo,
                            f"Regras do orçamento {orcamento.nome}")
    return definir_camada_do_orcamento(sessao, orcamento, nova)
