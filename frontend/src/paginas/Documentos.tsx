import { useState } from "react";
import { api, arquivo } from "../api";
import { Aviso, BotaoAcao, Carregando } from "../componentes";
import { cnpj, dataHora, reais, tamanho } from "../formatos";
import { useDados } from "../ganchos";
import type { Conferencia, Exportacao } from "../tipos";
import type { PropsDaAba } from "./Projeto";

const SITUACAO = { ok: "OK", atencao: "ATENÇÃO", problema: "PROBLEMA" };

function ComprovantePendente({ cnpj: numero, pagina, aoEnviar }: { cnpj: string; pagina: string; aoEnviar: () => void }) {
  const [pdf, setPdf] = useState<File | null>(null);
  const [avisos, setAvisos] = useState<string[]>([]);
  return (
    <tr>
      <td>{cnpj(numero)}</td>
      <td>
        <a className="botao secundario pequeno" href={pagina} target="_blank" rel="noreferrer noopener">1. Abrir na Receita</a>
      </td>
      <td>
        <div className="linha-campos">
          <input type="file" accept="application/pdf,.pdf" aria-label={`PDF do comprovante de ${cnpj(numero)}`}
            onChange={(e) => setPdf(e.target.files?.[0] ?? null)} />
          <BotaoAcao classe="pequeno" aoClicar={async () => {
            if (!pdf) throw new Error("Escolha o PDF do comprovante.");
            const dados = new FormData();
            dados.append("arquivo", pdf);
            dados.append("cnpj", numero);
            const r = await api.enviar<{ avisos: string[] }>("/api/comprovantes/pdf", dados);
            setAvisos(r.avisos);
            aoEnviar();
          }}>2. Enviar o PDF</BotaoAcao>
        </div>
        {avisos.length > 0 && <Aviso tipo="atencao"><ul>{avisos.map((a) => <li key={a}>{a}</li>)}</ul></Aviso>}
      </td>
    </tr>
  );
}

export function AbaDocumentos({ projeto, versao, atualizar }: PropsDaAba) {
  const conformidade = useDados<{ conferencias: Conferencia[]; pendencias: string | null }>(`/api/projetos/${projeto.id}/conformidade`, versao);
  const exportacoes = useDados<Exportacao[]>(`/api/projetos/${projeto.id}/exportacoes`, versao);
  const comprovantes = useDados<{ pendentes: string[]; paginas: Record<string, string> }>(
    `/api/projetos/${projeto.id}/comprovantes-pendentes`, versao);
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
          Cada CNPJ usado precisa do comprovante de inscrição e situação cadastral (D-13). Um comprovante vale para vários
          projetos por alguns dias (D-14). A Receita só aceita a verificação feita no seu navegador de sempre, então:
        </p>
        <ol className="pequeno">
          <li>Clique em <strong>Abrir na Receita</strong>: a página abre no seu navegador, com o CNPJ já preenchido.</li>
          <li>Resolva a verificação e clique em <strong>Consultar</strong>.</li>
          <li>Na página do comprovante, aperte <strong>Ctrl+P</strong> e escolha <strong>Salvar como PDF</strong>, com
            “Cabeçalhos e rodapés” ligado.</li>
          <li>Volte aqui, escolha o arquivo e clique em <strong>Enviar o PDF</strong>. O sistema confere se é o comprovante
            daquele CNPJ e lê a data de emissão.</li>
        </ol>
        {comprovantes.erro && <Aviso tipo="erro">{comprovantes.erro}</Aviso>}
        {comprovantes.dados && pendentes.length === 0 && <Aviso tipo="ok">Nenhum comprovante pendente.</Aviso>}
        {pendentes.length > 0 && (
          <table className="tabela">
            <tbody>
              {pendentes.map((c) => (
                <ComprovantePendente key={c} cnpj={c} pagina={comprovantes.dados!.paginas[c]} aoEnviar={atualizar} />
              ))}
            </tbody>
          </table>
        )}
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
