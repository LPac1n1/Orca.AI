import { api, arquivo } from "../api";
import { Aviso, BotaoAcao, Carregando } from "../componentes";
import { cnpj, dataHora, reais, tamanho } from "../formatos";
import { useDados } from "../ganchos";
import type { Conferencia, Exportacao } from "../tipos";
import type { PropsDaAba } from "./Projeto";

const SITUACAO = { ok: "OK", atencao: "ATENÇÃO", problema: "PROBLEMA" };

export function AbaDocumentos({ projeto, versao, atualizar }: PropsDaAba) {
  const conformidade = useDados<{ conferencias: Conferencia[]; pendencias: string | null }>(`/api/projetos/${projeto.id}/conformidade`, versao);
  const exportacoes = useDados<Exportacao[]>(`/api/projetos/${projeto.id}/exportacoes`, versao);
  const comprovantes = useDados<{ pendentes: string[] }>(`/api/projetos/${projeto.id}/comprovantes-pendentes`, versao);
  const pendentes = comprovantes.dados?.pendentes ?? [];
  const c = conformidade.dados;
  const problemas = c?.conferencias.filter((x) => x.situacao === "problema").length ?? 0;
  return (
    <div>
      <p className="explicacao">
        O pacote traz as planilhas (grade comparativa e plano de aplicação, com fórmulas), os orçamentos 1, 2, 3 e final,
        as cotações com as páginas capturadas e os comprovantes, a memória de cálculo, a conformidade, o histórico e o manifesto
        com a impressão digital de cada arquivo.
      </p>

      <div className="bloco">
        <h2>Comprovantes da Receita</h2>
        <p className="discreto">
          Cada CNPJ usado precisa do comprovante de inscrição e situação cadastral (D-13). A página da Receita pede uma
          verificação que só uma pessoa resolve: o sistema abre a página com o CNPJ preenchido, você resolve a verificação e
          clica em “Consultar”, e o comprovante é salvo sozinho. Um comprovante vale para vários projetos por alguns dias (D-14).
        </p>
        {comprovantes.erro && <Aviso tipo="erro">{comprovantes.erro}</Aviso>}
        {comprovantes.dados && pendentes.length === 0 && <Aviso tipo="ok">Nenhum comprovante pendente.</Aviso>}
        {pendentes.length > 0 && (
          <table className="tabela">
            <tbody>
              {pendentes.map((c) => (
                <tr key={c}>
                  <td>{cnpj(c)}</td>
                  <td>
                    <BotaoAcao classe="secundario pequeno" aoClicar={async () => {
                      await api.criar("/api/comprovantes", { cnpj: c, projeto_id: projeto.id });
                      atualizar();
                    }}>Emitir comprovante</BotaoAcao>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {pendentes.length > 1 && <p className="discreto pequeno">Um de cada vez: o próximo abre quando o anterior terminar.</p>}
      </div>

      <div className="bloco">
        <h2>Conformidade</h2>
        {conformidade.erro && <Aviso tipo="erro">{conformidade.erro}</Aviso>}
        {!c && !conformidade.erro && <Carregando />}
        {c?.pendencias && <Aviso tipo="atencao">{c.pendencias}</Aviso>}
        {c && c.conferencias.length > 0 && (
          <table className="tabela">
            <tbody>
              {c.conferencias.map((x) => (
                <tr key={x.regra}>
                  <td className={`situacao ${x.situacao}`}>{SITUACAO[x.situacao]}</td>
                  <td>{x.regra}</td>
                  <td className="pequeno">{x.detalhes.length > 0 && <ul>{x.detalhes.map((d) => <li key={d}>{d}</li>)}</ul>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="bloco">
        <h2>Gerar os documentos</h2>
        {problemas > 0 && <Aviso tipo="atencao">A conformidade aponta {problemas} problema(s). Você pode gerar o pacote para conferir, mas ele ainda não está pronto para entregar.</Aviso>}
        <BotaoAcao aoClicar={async () => { await api.criar(`/api/projetos/${projeto.id}/exportar`); atualizar(); }}>Gerar pacote (ZIP)</BotaoAcao>
        <p className="discreto pequeno">Leva alguns segundos por item. O andamento aparece em Tarefas, ao lado.</p>
        {exportacoes.dados && exportacoes.dados.length > 0 && (
          <table className="tabela">
            <thead><tr><th>Gerado em</th><th className="n">Total</th><th className="n">Tamanho</th><th /></tr></thead>
            <tbody>
              {exportacoes.dados.map((x) => (
                <tr key={x.arquivo}>
                  <td>{dataHora(x.gerado_em)}</td>
                  <td className="n">{reais(x.total_centavos)}</td>
                  <td className="n">{tamanho(x.bytes)}</td>
                  <td><a className="botao secundario pequeno" href={arquivo(x.arquivo)} download>Baixar</a></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
