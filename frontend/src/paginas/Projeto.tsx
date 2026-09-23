import { useCallback, useState } from "react";
import { NavLink, Route, Routes, useParams } from "react-router-dom";
import { Aviso, Carregando } from "../componentes";
import { dataHora, reais, TIPOS_DE_TAREFA } from "../formatos";
import { useDados, useTarefas } from "../ganchos";
import type { Projeto, Tarefa } from "../tipos";
import { AbaCadastro } from "./Cadastro";
import { AbaDocumentos } from "./Documentos";
import { AbaHistorico } from "./Historico";
import { AbaPainel } from "./Painel";
import { AbaPesquisa } from "./Pesquisa";
import { AbaTeto } from "./Teto";

export interface PropsDaAba {
  projeto: Projeto;
  versao: number;
  atualizar: () => void; // depois de uma ação: recarrega os dados e as tarefas
}

function Tarefas({ tarefas }: { tarefas: Tarefa[] }) {
  const recentes = tarefas.slice(0, 8);
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
            {t.mensagem && <div className={t.estado === "falhou" ? "erro-curto" : "discreto"}>{t.mensagem}</div>}
            {typeof t.parametros.url === "string" && <div className="url">{t.parametros.url}</div>}
            <div className="discreto pequeno">{dataHora(t.concluida_em ?? t.criado_em)}</div>
          </li>
        ))}
      </ul>
    </aside>
  );
}

export function PaginaProjeto() {
  const { id } = useParams();
  const [versao, setVersao] = useState(0);
  const atualizar = useCallback(() => setVersao((v) => v + 1), []);
  const { dados: projeto, erro } = useDados<Projeto>(`/api/projetos/${id}`, versao);
  const { tarefas, emAndamento } = useTarefas(id!, atualizar, versao);

  if (erro) return <Aviso tipo="erro">{erro}</Aviso>;
  if (!projeto) return <Carregando />;
  const props: PropsDaAba = { projeto, versao, atualizar };
  const abas = [
    ["", "Painel"],
    ["cadastro", "Itens e cargos"],
    ["pesquisa", "Pesquisa e revisão"],
    ["teto", "Fechar o teto"],
    ["documentos", "Documentos"],
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
          </p>
        </div>
        {emAndamento && <span className="selo amarelo">trabalhando…</span>}
      </div>
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
            <Route path="historico" element={<AbaHistorico {...props} />} />
          </Routes>
        </div>
        <Tarefas tarefas={tarefas} />
      </div>
    </section>
  );
}
