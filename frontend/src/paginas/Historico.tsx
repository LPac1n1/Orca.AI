import { Aviso, Carregando } from "../componentes";
import { dataHora } from "../formatos";
import { useDados } from "../ganchos";
import type { Evento } from "../tipos";
import type { PropsDaAba } from "./Projeto";

const ACOES: Record<string, string> = { criar: "criou", alterar: "alterou", excluir: "excluiu", arquivar: "arquivou" };
const REGISTROS: Record<string, string> = {
  projeto: "projeto", orcamento: "orçamento", lote: "lote", item: "item", cargo: "cargo", observacao: "pesquisa",
  correspondencia: "correspondência", decisao: "decisão", execucao_otimizacao: "otimização", linha_final: "linha final",
  alerta: "alerta", cotacao: "cotação",
};

function resumo(e: Evento): string {
  const d = e.depois ?? {};
  const nome = (d.descricao ?? d.nome ?? d.tipo ?? "") as string;
  if (e.acao === "alterar" && e.antes) {
    return Object.keys(e.depois ?? {}).map((k) => `${k}: ${String(e.antes![k] ?? "—")} → ${String(d[k] ?? "—")}`).join("; ");
  }
  return nome;
}

export function AbaHistorico({ projeto, versao }: PropsDaAba) {
  const { dados, erro } = useDados<Evento[]>(`/api/projetos/${projeto.id}/historico`, versao);
  if (erro) return <Aviso tipo="erro">{erro}</Aviso>;
  if (!dados) return <Carregando />;
  return (
    <div>
      <p className="discreto">Tudo o que foi criado ou mudado, por quem e quando. Nada é apagado: registros de pesquisas, decisões e otimizações nunca mudam.</p>
      <table className="tabela">
        <thead><tr><th>Quando</th><th>Quem</th><th>O quê</th><th>Detalhe</th></tr></thead>
        <tbody>
          {dados.map((e) => (
            <tr key={e.id}>
              <td className="pequeno">{dataHora(e.criado_em)}</td>
              <td className="pequeno">{e.autor.replace("usuario:", "").replace("sistema:", "sistema · ")}</td>
              <td>{ACOES[e.acao] ?? e.acao} {REGISTROS[e.entidade] ?? e.entidade}</td>
              <td className="pequeno">{resumo(e)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
