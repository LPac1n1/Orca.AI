"""Descobrir o que uma loja vende (D-74): a busca dela é testada com produtos típicos de cada tipo.

Uma vez por loja (poucos pedidos, no ritmo das buscas). O resultado vai para o catálogo da OSC
(`categorias`, com a origem e a data); a pessoa pode corrigir no formulário da loja.
"""

import httpx

from orca.banco import sessao_como
from orca.busca import Consulta, ErroBusca, Ritmo, lojas_de_busca
from orca.busca.classificacao import AMOSTRAS, nomes, vende_o_tipo
from orca.coleta import ErroCaptura
from orca.coleta.catalogo import ler_catalogo_dados
from orca.fluxo.catalogos import diferenca_de_lojas, lojas_da_organizacao, salvar_lojas
from orca.tarefas.busca import _buscar
from orca.tarefas.fila import ErroTarefa, Fila, TarefaCancelada, tarefa


@tarefa("classificar_loja")
def classificar_loja(fila: Fila, tarefa_id: str, p: dict) -> dict:
    ctx = fila.contexto
    cancelamento = fila.cancelamento(tarefa_id)
    with sessao_como(ctx.fabrica, "sistema:lojas") as s:
        loja = next((l for l in lojas_de_busca(lojas_da_organizacao(s, p["organizacao_id"])) if l.id == p["loja_id"]), None)
    if loja is None or not loja.automatica:
        raise ErroTarefa("A loja não tem busca automática: o sistema aprende o que ela vende com as páginas que você "
                         "confirmar nas pesquisas.")
    ritmo = Ritmo(ctx.intervalo_busca_s)
    cliente = ctx.cliente_http() if ctx.cliente_http else httpx.Client()
    vende = []
    try:
        for n, (categoria, termos) in enumerate(AMOSTRAS.items()):
            if cancelamento.is_set():
                raise TarefaCancelada()
            fila.progresso(tarefa_id, int(95 * n / len(AMOSTRAS)), f"{loja.nome}: {termos[0]}")
            for termo in termos:
                try:
                    candidatos = _buscar(fila, cliente, ritmo, loja, Consulta(termo))
                except (ErroBusca, ErroCaptura) as erro:
                    raise ErroTarefa(f"A busca da {loja.nome} não respondeu: {str(erro).splitlines()[0]}") from erro
                if vende_o_tipo(termo, candidatos):
                    vende.append(categoria)
                    break
    finally:
        cliente.close()

    with sessao_como(ctx.fabrica, "sistema:lojas") as s:
        editado = lojas_da_organizacao(s, p["organizacao_id"])
        for entrada in editado.get("lojas") or []:
            if entrada["id"] == loja.id:
                entrada.update(categorias=vende, categorias_origem="automatica", categorias_em=ctx.hoje().isoformat())
        salvar_lojas(s, p["organizacao_id"], diferenca_de_lojas(ler_catalogo_dados(), editado),
                     f"o sistema descobriu o que {loja.nome} vende")
    mensagem = (f"{loja.nome} vende: " + ", ".join(nomes(vende))) if vende else \
        f"a busca da {loja.nome} não trouxe produtos típicos de nenhum tipo"
    return {"loja_id": loja.id, "categorias": vende, "mensagem": mensagem}
