import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api";
import { Aviso, Campo, Carregando, Formulario, Modal } from "../componentes";
import { centavosDeTexto, data, reais } from "../formatos";
import { useDados } from "../ganchos";
import type { Organizacao, Projeto } from "../tipos";

function NovoProjeto({ aoFechar }: { aoFechar: () => void }) {
  const navegar = useNavigate();
  const { dados: organizacoes } = useDados<Organizacao[]>("/api/organizacoes");
  const [org, setOrg] = useState("");
  const [novaOrg, setNovaOrg] = useState("");
  const [cnpjOrg, setCnpjOrg] = useState("");
  const [nome, setNome] = useState("");
  const [teto, setTeto] = useState("");
  const [duracao, setDuracao] = useState("12");
  const [orgao, setOrgao] = useState("");
  const [instrumento, setInstrumento] = useState("");
  const [processo, setProcesso] = useState("");
  const [cep, setCep] = useState("");
  const [entrega, setEntrega] = useState("");
  const criarOrg = org === "" && (organizacoes?.length ?? 0) === 0 ? true : org === "__nova__";

  async function enviar() {
    const teto_centavos = centavosDeTexto(teto);
    if (!teto_centavos) throw new Error("Informe o teto em reais, por exemplo 150.000,00.");
    let organizacao_id = org;
    if (criarOrg) {
      if (!novaOrg.trim()) throw new Error("Informe o nome da organização (OSC).");
      organizacao_id = (await api.criar<Organizacao>("/api/organizacoes", { nome: novaOrg, cnpj: cnpjOrg || null })).id;
    }
    if (!organizacao_id) throw new Error("Escolha a organização.");
    const projeto = await api.criar<Projeto>("/api/projetos", {
      organizacao_id, nome, teto_centavos, duracao_meses: Number(duracao),
      orgao: orgao || null, instrumento: instrumento || null, processo: processo || null,
      cep: cep || null, data_entrega: entrega || null,
    });
    navegar(`/projetos/${projeto.id}/cadastro`);
  }

  return (
    <Modal titulo="Novo projeto" aoFechar={aoFechar}>
      <Formulario aoEnviar={enviar} rotulo="Criar projeto" aoCancelar={aoFechar}>
        {(organizacoes?.length ?? 0) > 0 && (
          <Campo rotulo="Organização (OSC)">
            <select value={org} onChange={(e) => setOrg(e.target.value)} required>
              <option value="">Escolha…</option>
              {organizacoes!.map((o) => <option key={o.id} value={o.id}>{o.nome}</option>)}
              <option value="__nova__">+ Nova organização</option>
            </select>
          </Campo>
        )}
        {criarOrg && (
          <div className="linha-campos">
            <Campo rotulo="Nome da organização"><input value={novaOrg} onChange={(e) => setNovaOrg(e.target.value)} /></Campo>
            <Campo rotulo="CNPJ da organização" ajuda="opcional"><input value={cnpjOrg} onChange={(e) => setCnpjOrg(e.target.value)} /></Campo>
          </div>
        )}
        <Campo rotulo="Nome do projeto"><input value={nome} onChange={(e) => setNome(e.target.value)} required /></Campo>
        <div className="linha-campos">
          <Campo rotulo="Teto do projeto (R$)" ajuda="O orçamento fecha exatamente neste valor.">
            <input value={teto} onChange={(e) => setTeto(e.target.value)} placeholder="150.000,00" inputMode="decimal" required />
          </Campo>
          <Campo rotulo="Duração (meses)">
            <input type="number" min={1} max={120} value={duracao} onChange={(e) => setDuracao(e.target.value)} required />
          </Campo>
        </div>
        <div className="linha-campos">
          <Campo rotulo="Órgão ou secretaria"><input value={orgao} onChange={(e) => setOrgao(e.target.value)} /></Campo>
          <Campo rotulo="Instrumento" ajuda="termo de fomento, colaboração, emenda…"><input value={instrumento} onChange={(e) => setInstrumento(e.target.value)} /></Campo>
        </div>
        <div className="linha-campos">
          <Campo rotulo="Nº do processo"><input value={processo} onChange={(e) => setProcesso(e.target.value)} /></Campo>
          <Campo rotulo="CEP de referência"><input value={cep} onChange={(e) => setCep(e.target.value)} placeholder="00000-000" /></Campo>
          <Campo rotulo="Entrega prevista" ajuda="confere a validade das pesquisas">
            <input type="date" value={entrega} onChange={(e) => setEntrega(e.target.value)} />
          </Campo>
        </div>
      </Formulario>
    </Modal>
  );
}

export function PaginaProjetos() {
  const [arquivados, setArquivados] = useState(false);
  const { dados, erro } = useDados<Projeto[]>(`/api/projetos?arquivados=${arquivados}`);
  const [criando, setCriando] = useState(false);
  return (
    <section>
      <div className="cabecalho-pagina">
        <h1>Projetos</h1>
        <label className="marcador"><input type="checkbox" checked={arquivados} onChange={(e) => setArquivados(e.target.checked)} /> mostrar arquivados</label>
        <button onClick={() => setCriando(true)}>+ Novo projeto</button>
      </div>
      {erro && <Aviso tipo="erro">{erro}</Aviso>}
      {!dados && !erro && <Carregando />}
      {dados?.length === 0 && (
        <div className="vazio">
          <p>Nenhum projeto ainda.</p>
          <p className="discreto">Crie um projeto com o teto e a duração. Depois cadastre os orçamentos (rubricas), os itens e os cargos, e cole os links das lojas e das vagas.</p>
        </div>
      )}
      <div className="cartoes">
        {dados?.map((p) => (
          <Link key={p.id} to={`/projetos/${p.id}`} className="cartao">
            <strong>{p.nome}</strong>
            <span className="discreto">{p.organizacao.nome}{p.orgao ? ` · ${p.orgao}` : ""}</span>
            <span className="grande">{reais(p.teto_centavos)}</span>
            <span className="discreto">{p.duracao_meses} meses{p.data_entrega ? ` · entrega ${data(p.data_entrega)}` : ""}{p.arquivado ? " · arquivado" : ""}</span>
          </Link>
        ))}
      </div>
      {criando && <NovoProjeto aoFechar={() => setCriando(false)} />}
    </section>
  );
}
