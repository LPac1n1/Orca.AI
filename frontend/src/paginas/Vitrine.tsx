import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import { Aviso, BotaoAcao, Modal } from "../componentes";
import { reais } from "../formatos";
import { ativa, useTarefa } from "../ganchos";
import type { Status, Tarefa } from "../tipos";

// Vitrine do item (D-75, "código de barras primeiro"): a pessoa escolhe o produto certo entre os achados.

interface ProdutoNaVitrine {
  url: string;
  titulo: string;
  marca: string | null;
  preco_centavos: number | null;
  imagem: string | null;
  ean: string | null;
  status: Status;
}

interface ResultadoDaVitrine {
  termo: string;
  lojas: { loja_id: string; loja: string; produtos: ProdutoNaVitrine[] }[];
  avisos: string[];
  mensagem: string;
}

function FotoDoProduto({ src, alt }: { src: string | null; alt: string }) {
  const [erro, setErro] = useState(false);
  if (!src || erro) return <div className="foto vazia">sem foto</div>;
  return <img className="foto" src={src} alt={alt} loading="lazy" referrerPolicy="no-referrer" onError={() => setErro(true)} />;
}

export function VitrineDoItem({ item, tarefaId, aoIniciar, aoFechar, atualizar }: {
  item: { id: string; descricao: string; marca: string | null; apresentacao?: string | null };
  tarefaId: string | null;
  aoIniciar: (tarefaId: string) => void;
  aoFechar: () => void;
  atualizar: () => void;
}) {
  const tarefa = useTarefa(tarefaId);
  const [escolhido, setEscolhido] = useState<string | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const iniciou = useRef(false);
  const procurar = async () => {
    setErro(null);
    try {
      aoIniciar((await api.criar<Tarefa>(`/api/itens/${item.id}/vitrine`)).id);
    } catch (e) {
      setErro((e as Error).message);
    }
  };
  useEffect(() => {  // abre já procurando (uma vez)
    if (!tarefaId && !iniciou.current) {
      iniciou.current = true;
      void procurar();
    }
  });
  const resultado = tarefa?.estado === "concluida" ? (tarefa.resultado as unknown as ResultadoDaVitrine) : null;
  return (
    <Modal titulo={`Escolher o produto — ${item.descricao}${item.marca ? ` (${item.marca})` : ""}`} aoFechar={aoFechar}>
      <p className="explicacao">
        O sistema procura o item nas lojas que vendem esse tipo de produto e mostra o que achou. Clique em <strong>É este</strong> no produto
        certo (confira marca, tamanho e quantidade). A página dele vira a prova e o <strong>produto de referência</strong>: o
        código de barras dele passa a guiar as buscas nas outras lojas, e o mesmo código vira 🟢 sozinho (D-71, D-75).
      </p>
      {erro && <Aviso tipo="erro">{erro}</Aviso>}
      {tarefaId && (!tarefa || ativa(tarefa)) && (
        <Aviso tipo="info">Procurando nas lojas… {tarefa?.mensagem ?? ""} {tarefa ? `(${tarefa.progresso}%)` : ""}</Aviso>
      )}
      {tarefa && (tarefa.estado === "falhou" || tarefa.estado === "cancelada") && (
        <Aviso tipo="erro">{tarefa.mensagem ?? "A busca não terminou."}</Aviso>
      )}
      {escolhido && (
        <Aviso tipo="ok">
          Escolhido. A página está sendo guardada como prova (quadro Tarefas); em seguida vira o produto de referência. Use
          “Fechar o lote” para o sistema procurar o mesmo código de barras nas outras lojas.
        </Aviso>
      )}
      {resultado && (
        <>
          <p className="discreto pequeno">Busca por “{resultado.termo}” · {resultado.mensagem}</p>
          {resultado.avisos.length > 0 && <ul className="pequeno">{resultado.avisos.map((a) => <li key={a}>{a}</li>)}</ul>}
          {resultado.lojas.map((g) => (
            <div key={g.loja_id} className="bloco">
              <h3>{g.loja} <span className="discreto pequeno">· {g.produtos.length} produto(s)</span></h3>
              {g.produtos.length === 0 && <p className="discreto pequeno">Nada parecido nesta loja.</p>}
              <div className="cartoes-produto">
                {g.produtos.map((p) => (
                  <div key={p.url} className={`cartao-produto ${escolhido === p.url ? "referencia" : ""}`}>
                    <FotoDoProduto src={p.imagem} alt={p.titulo} />
                    <span className="pequeno">{p.titulo}</span>
                    <span>{p.preco_centavos ? reais(p.preco_centavos) : <span className="discreto pequeno">preço na página</span>}</span>
                    {p.ean && <span className="discreto pequeno">código {p.ean}</span>}
                    <a className="pequeno" href={p.url} target="_blank" rel="noreferrer noopener">abrir a página</a>
                    {!escolhido && (
                      <BotaoAcao classe="pequeno" aoClicar={async () => {
                        await api.criar(`/api/itens/${item.id}/escolher-produto`, { url: p.url });
                        setEscolhido(p.url);
                        atualizar();
                      }}>É este</BotaoAcao>
                    )}
                  </div>
                ))}
              </div>
            </div>
          ))}
          <p className="discreto pequeno">
            Não achou? Se você tem o produto em mãos, digite o código de barras da embalagem no item (“editar”), ou cole o
            link da página do produto em “Pesquisa”.
          </p>
          <div className="acoes">
            <button className="secundario" onClick={aoFechar}>Fechar</button>
            <BotaoAcao classe="secundario" aoClicar={procurar}>Procurar de novo</BotaoAcao>
          </div>
        </>
      )}
    </Modal>
  );
}
