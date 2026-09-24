import { Link } from "react-router-dom";
import { api } from "../api";
import { Aviso, BotaoAcao, Carregando, Selo } from "../componentes";
import { reais } from "../formatos";
import { useDados } from "../ganchos";
import type { Painel } from "../tipos";
import type { PropsDaAba } from "./Projeto";

export function AbaPainel({ projeto, versao, atualizar }: PropsDaAba) {
  const { dados: p, erro } = useDados<Painel>(`/api/projetos/${projeto.id}/painel`, versao);
  if (erro) return <Aviso tipo="erro">{erro}</Aviso>;
  if (!p) return <Carregando />;
  const fechado = p.total_centavos !== null;
  const base = `/projetos/${projeto.id}`;
  return (
    <div className="painel">
      <div className="numeros">
        <div className="numero"><span>Teto</span><strong>{reais(p.teto_centavos)}</strong></div>
        <div className="numero">
          <span>{fechado ? "Total do orçamento" : "Planejado até agora"}</span>
          <strong>{reais(fechado ? p.total_centavos : p.planejado_centavos)}</strong>
        </div>
        <div className={`numero ${fechado && p.diferenca_centavos === 0 ? "ok" : ""}`}>
          <span>Diferença para o teto</span>
          <strong>{fechado ? reais(p.diferenca_centavos) : "teto não fechado"}</strong>
        </div>
        <div className="numero">
          <span>Itens e cargos</span>
          <strong className="contagem">
            <Selo status="verde" texto={`${p.contagem.verde} prontos`} />
            <Selo status="amarelo" texto={`${p.contagem.amarelo} revisar`} />
            <Selo status="vermelho" texto={`${p.contagem.vermelho} problema`} />
          </strong>
        </div>
        <div className="numero"><span>CNPJs ativos</span><strong>{p.cnpjs_ativos} de {p.cnpjs}</strong></div>
      </div>

      {p.alertas.length > 0 && (
        <div className="bloco">
          <h2>O que precisa de atenção</h2>
          <ul className="alertas">{p.alertas.map((a) => <li key={a}>{a}</li>)}</ul>
        </div>
      )}

      <div className="bloco">
        <h2>Próximos passos</h2>
        <ol className="passos">
          <li>Cadastre os orçamentos, lotes, itens e cargos em <Link to={`${base}/cadastro`}>Itens e cargos</Link>.</li>
          <li>Cole os links das lojas e das vagas em <Link to={`${base}/pesquisa`}>Pesquisa e revisão</Link> e confira cada resultado.</li>
          <li>
            Consulte a situação dos CNPJs:{" "}
            <BotaoAcao classe="secundario pequeno" aoClicar={async () => { await api.criar(`/api/projetos/${projeto.id}/consultar-cnpjs`); atualizar(); }}>
              Consultar {p.cnpjs_sem_consulta.length > 0 ? `${p.cnpjs_sem_consulta.length} CNPJ(s)` : "CNPJs"}
            </BotaoAcao>
          </li>
          <li>Emita os comprovantes da Receita de cada CNPJ em <Link to={`${base}/documentos`}>Documentos</Link> (no seu navegador; depois envie o PDF).</li>
          <li>Feche o teto em <Link to={`${base}/teto`}>Fechar o teto</Link> e gere os documentos em <Link to={`${base}/documentos`}>Documentos</Link>.</li>
        </ol>
      </div>

      <div className="bloco">
        <h2>Situação de cada linha</h2>
        {p.linhas.length === 0 && <p className="discreto">Nenhum item ou cargo cadastrado ainda.</p>}
        <table className="tabela">
          <tbody>
            {p.linhas.map((l) => (
              <tr key={l.id}>
                <td><Selo status={l.status} /></td>
                <td>{l.nome} <span className="discreto">({l.tipo})</span></td>
                <td className="discreto">{l.motivos.join(" · ")}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
