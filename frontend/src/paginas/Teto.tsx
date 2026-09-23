import { api } from "../api";
import { Aviso, BotaoAcao, Carregando } from "../componentes";
import { dataHora, horas, reais } from "../formatos";
import { useDados } from "../ganchos";
import type { Execucao } from "../tipos";
import type { PropsDaAba } from "./Projeto";

const SITUACAO = { otima: "teto fechado (melhor solução)", viavel: "teto fechado (solução válida)", sem_solucao: "não foi possível fechar" };

function valor(unidade: string, v: number) {
  return unidade === "un" ? `${v} un` : `${horas(v)} h/mês`;
}

export function AbaTeto({ projeto, versao, atualizar }: PropsDaAba) {
  const { dados, erro } = useDados<{ ultima: Execucao | null; pendencias: string[] }>(`/api/projetos/${projeto.id}/otimizacao`, versao);
  if (erro) return <Aviso tipo="erro">{erro}</Aviso>;
  if (!dados) return <Carregando />;
  const e = dados.ultima;
  return (
    <div>
      <p className="explicacao">
        O sistema ajusta só quantidades e horas por mês, dentro das margens de cada linha (padrão ±20%, nunca além da jornada legal),
        para o total ficar <strong>exatamente</strong> em {reais(projeto.teto_centavos)}. Preços não mudam, e cada loja escolhida continua a de menor total.
        Uma verificação independente refaz todas as contas.
      </p>
      {dados.pendencias.length > 0 ? (
        <Aviso tipo="atencao">
          <p>Antes de fechar o teto, resolva:</p>
          <ul>{dados.pendencias.map((p) => <li key={p}>{p}</li>)}</ul>
        </Aviso>
      ) : (
        <BotaoAcao aoClicar={async () => { await api.criar(`/api/projetos/${projeto.id}/fechar-teto`); atualizar(); }}>
          {e?.vigente ? "Fechar o teto de novo" : "Fechar o teto"}
        </BotaoAcao>
      )}

      {e && (
        <div className="bloco">
          <h2>Última otimização <span className="discreto">· {dataHora(e.criado_em)}</span></h2>
          {!e.vigente && e.status !== "sem_solucao" && <Aviso tipo="atencao">Algo mudou depois desta otimização (preço, quantidade, loja ou regra). Feche o teto de novo.</Aviso>}
          <p>
            <strong>{SITUACAO[e.status]}</strong>
            {e.total_centavos !== null && <> · total {reais(e.total_centavos)} de {reais(e.teto_centavos)}</>}
            {e.status !== "sem_solucao" && <> · verificação independente {e.verificacao_ok ? "sem problemas" : "com problemas"}</>}
          </p>
          {e.status === "sem_solucao" && (
            <Aviso tipo="erro">
              <p>{e.resultado.mensagem}</p>
              {e.resultado.sugestoes && e.resultado.sugestoes.length > 0 && (
                <>
                  <p>Sugestões (a menor mudança primeiro):</p>
                  <ul>{e.resultado.sugestoes.map((s) => <li key={s.mensagem}>{s.mensagem}</li>)}</ul>
                </>
              )}
            </Aviso>
          )}
          {(e.resultado.verificacao ?? []).length > 0 && <Aviso tipo="erro"><ul>{e.resultado.verificacao!.map((v) => <li key={v}>{v}</li>)}</ul></Aviso>}
          {(e.resultado.alteracoes ?? []).length > 0 ? (
            <table className="tabela">
              <thead><tr><th>Linha ajustada</th><th className="n">Planejado</th><th className="n">Final</th></tr></thead>
              <tbody>
                {e.resultado.alteracoes!.map((a) => (
                  <tr key={a.linha}><td>{a.nome}</td><td className="n">{valor(a.unidade, a.de)}</td><td className="n">{valor(a.unidade, a.para)}</td></tr>
                ))}
              </tbody>
            </table>
          ) : e.status !== "sem_solucao" && <p className="discreto">Nenhuma linha precisou ser ajustada.</p>}
        </div>
      )}
    </div>
  );
}
