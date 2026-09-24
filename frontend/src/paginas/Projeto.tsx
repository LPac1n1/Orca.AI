import { useCallback, useState } from "react";
import { Link, NavLink, Route, Routes, useParams } from "react-router-dom";
import { api } from "../api";
import { Aviso, BotaoAcao, Campo, Carregando, Formulario, Modal } from "../componentes";
import { centavosDeTexto, data, dataHora, reais, textoDeCentavos, TIPOS_DE_TAREFA } from "../formatos";
import { useDados, useTarefas } from "../ganchos";
import type { Projeto, Tarefa } from "../tipos";
import { AbaCadastro } from "./Cadastro";
import { AbaDocumentos } from "./Documentos";
import { AbaHistorico } from "./Historico";
import { AbaPainel } from "./Painel";
import { AbaPesquisa } from "./Pesquisa";
import { AbaRegras } from "./Regras";
import { AbaTeto } from "./Teto";

export interface PropsDaAba {
  projeto: Projeto;
  versao: number;
  atualizar: () => void; // depois de uma ação: recarrega os dados e as tarefas
}

const PODE_CANCELAR = new Set(["pendente", "esperando_usuario"]);

function Tarefas({ tarefas, atualizar }: { tarefas: Tarefa[]; atualizar: () => void }) {
  const recentes = tarefas.slice(0, 8);
  const acao = (caminho: string) => async () => { await api.criar(caminho); atualizar(); };
  if (recentes.length === 0) return null;
  return (
    <aside className="tarefas">
      <h3>Tarefas</h3>
      <ul>
        {recentes.map((t) => (
          <li key={t.id} className={`tarefa ${t.estado}`}>
            <div className="tarefa-titulo">
              <span>{TIPOS_DE_TAREFA[t.tipo] ?? t.tipo}</span>
              <span className="discreto">{{ pendente: "na fila", rodando: `${t.progresso}%`, esperando_usuario: "esperando você",
                concluida: "feita", falhou: "falhou", cancelada: "cancelada" }[t.estado]}</span>
            </div>
            {t.estado === "rodando" && <div className="barra"><div style={{ width: `${t.progresso}%` }} /></div>}
            {t.mensagem && <div className={t.estado === "falhou" ? "erro-curto" : t.estado === "esperando_usuario" ? "" : "discreto"}>{t.mensagem}</div>}
            {Boolean(t.resultado?.bloqueio) && (
              <div className="erro-curto pequeno">A loja recusou o programa. Cole o link de novo e escolha “Abrir numa janela para eu navegar”.</div>
            )}
            {PODE_CANCELAR.has(t.estado) && (
              <div className="botoes">
                {t.tipo === "captura_assistida" && t.estado === "esperando_usuario" && (
                  <BotaoAcao classe="pequeno" aoClicar={acao(`/api/tarefas/${t.id}/capturar-agora`)}>Capturar agora</BotaoAcao>
                )}
                <BotaoAcao classe="secundario pequeno" aoClicar={acao(`/api/tarefas/${t.id}/cancelar`)}>Cancelar</BotaoAcao>
              </div>
            )}
            {typeof t.parametros.url === "string" && <div className="url">{t.parametros.url}</div>}
            <div className="discreto pequeno">{dataHora(t.concluida_em ?? t.criado_em)}</div>
          </li>
        ))}
      </ul>
    </aside>
  );
}

function EditarProjeto({ projeto, aoFechar, aoSalvar }: { projeto: Projeto; aoFechar: () => void; aoSalvar: () => void }) {
  const [v, setV] = useState({
    nome: projeto.nome, teto: textoDeCentavos(projeto.teto_centavos), duracao: String(projeto.duracao_meses),
    orgao: projeto.orgao ?? "", instrumento: projeto.instrumento ?? "", processo: projeto.processo ?? "",
    cep: projeto.cep ? `${projeto.cep.slice(0, 5)}-${projeto.cep.slice(5)}` : "", entrega: projeto.data_entrega ?? "",
  });
  const campo = (chave: keyof typeof v) => (e: { target: { value: string } }) => setV({ ...v, [chave]: e.target.value });
  return (
    <Modal titulo="Dados do projeto" aoFechar={aoFechar}>
      <Formulario aoCancelar={aoFechar} aoEnviar={async () => {
        const teto_centavos = centavosDeTexto(v.teto);
        if (!teto_centavos) throw new Error("Informe o teto em reais, por exemplo 150.000,00.");
        await api.mudar(`/api/projetos/${projeto.id}`, {
          nome: v.nome, teto_centavos, duracao_meses: Number(v.duracao), orgao: v.orgao || null,
          instrumento: v.instrumento || null, processo: v.processo || null, cep: v.cep || null, data_entrega: v.entrega || null,
        });
        aoSalvar();
        aoFechar();
      }}>
        <Campo rotulo="Nome do projeto"><input value={v.nome} onChange={campo("nome")} required /></Campo>
        <div className="linha-campos">
          <Campo rotulo="Teto do projeto (R$)" ajuda="Mudar o teto desatualiza o fechamento: feche o teto de novo.">
            <input value={v.teto} onChange={campo("teto")} inputMode="decimal" required />
          </Campo>
          <Campo rotulo="Duração (meses)"><input type="number" min={1} max={120} value={v.duracao} onChange={campo("duracao")} required /></Campo>
        </div>
        <div className="linha-campos">
          <Campo rotulo="Órgão ou secretaria"><input value={v.orgao} onChange={campo("orgao")} /></Campo>
          <Campo rotulo="Instrumento"><input value={v.instrumento} onChange={campo("instrumento")} /></Campo>
        </div>
        <div className="linha-campos">
          <Campo rotulo="Nº do processo"><input value={v.processo} onChange={campo("processo")} /></Campo>
          <Campo rotulo="CEP de referência"><input value={v.cep} onChange={campo("cep")} placeholder="00000-000" /></Campo>
          <Campo rotulo="Entrega prevista" ajuda="confere a validade das pesquisas"><input type="date" value={v.entrega} onChange={campo("entrega")} /></Campo>
        </div>
      </Formulario>
    </Modal>
  );
}

export function PaginaProjeto() {
  const { id } = useParams();
  const [versao, setVersao] = useState(0);
  const atualizar = useCallback(() => setVersao((v) => v + 1), []);
  const { dados: projeto, erro } = useDados<Projeto>(`/api/projetos/${id}`, versao);
  const { tarefas, emAndamento, atualizar: atualizarTarefas } = useTarefas(id!, atualizar, versao);
  const [editando, setEditando] = useState(false);

  if (erro) return <Aviso tipo="erro">{erro}</Aviso>;
  if (!projeto) return <Carregando />;
  const props: PropsDaAba = { projeto, versao, atualizar };
  const abas = [
    ["", "Painel"],
    ["cadastro", "Itens e cargos"],
    ["pesquisa", "Pesquisa e revisão"],
    ["teto", "Fechar o teto"],
    ["documentos", "Documentos"],
    ["regras", "Regras"],
    ["historico", "Histórico"],
  ];
  return (
    <section className="projeto">
      <div className="cabecalho-pagina">
        <div>
          <h1>{projeto.nome}</h1>
          <p className="discreto">
            {projeto.organizacao.nome} · teto {reais(projeto.teto_centavos)} · {projeto.duracao_meses} meses
            {projeto.orgao ? ` · ${projeto.orgao}` : ""}
            {projeto.cep ? ` · CEP ${projeto.cep.slice(0, 5)}-${projeto.cep.slice(5)}` : " · sem CEP"}
            {projeto.data_entrega ? ` · entrega ${data(projeto.data_entrega)}` : ""}
            {" · "}<button className="link" onClick={() => setEditando(true)}>editar dados</button>
            {" · "}<Link to={`/catalogos/${projeto.organizacao.id}`}>catálogos da OSC</Link>
          </p>
        </div>
        {emAndamento && <span className="selo amarelo">trabalhando…</span>}
      </div>
      {editando && <EditarProjeto projeto={projeto} aoFechar={() => setEditando(false)} aoSalvar={atualizar} />}
      <nav className="abas">
        {abas.map(([caminho, rotulo]) => (
          <NavLink key={caminho} to={`/projetos/${id}/${caminho}`} end={caminho === ""}>{rotulo}</NavLink>
        ))}
      </nav>
      <div className={tarefas.length > 0 ? "com-lateral" : ""}>
        <div className="principal">
          <Routes>
            <Route index element={<AbaPainel {...props} />} />
            <Route path="cadastro" element={<AbaCadastro {...props} />} />
            <Route path="pesquisa" element={<AbaPesquisa {...props} />} />
            <Route path="teto" element={<AbaTeto {...props} />} />
            <Route path="documentos" element={<AbaDocumentos {...props} />} />
            <Route path="regras" element={<AbaRegras {...props} />} />
            <Route path="historico" element={<AbaHistorico {...props} />} />
          </Routes>
        </div>
        <Tarefas tarefas={tarefas} atualizar={() => { atualizarTarefas(); atualizar(); }} />
      </div>
    </section>
  );
}
