import { useState } from "react";
import { api } from "../api";
import { BotaoAcao, Campo, Formulario, Modal } from "../componentes";
import { centesimosDeTexto, horas, REGIMES, TIPOS_DE_ORCAMENTO } from "../formatos";
import { useDados } from "../ganchos";
import type { Cargo, Categoria, Item, Jornada, Orcamento } from "../tipos";
import type { PropsDaAba } from "./Projeto";

type Janela =
  | { tipo: "orcamento" }
  | { tipo: "lote"; orcamento: Orcamento }
  | { tipo: "item"; loteId: string; item?: Item; trocar?: boolean }
  | { tipo: "cargo"; orcamentoId: string; cargo?: Cargo };

function numeroOuNulo(texto: string): number | null {
  return texto.trim() === "" ? null : Number(texto);
}

function FormOrcamento({ projetoId, aoTerminar }: { projetoId: string; aoTerminar: () => void }) {
  const [nome, setNome] = useState("");
  const [tipo, setTipo] = useState<Orcamento["tipo"]>("materiais");
  return (
    <Formulario rotulo="Criar orçamento" aoCancelar={aoTerminar}
      aoEnviar={async () => { await api.criar(`/api/projetos/${projetoId}/orcamentos`, { nome, tipo }); aoTerminar(); }}>
      <Campo rotulo="Nome da rubrica" ajuda="ex.: Material pedagógico, Alimentação, Recursos humanos">
        <input value={nome} onChange={(e) => setNome(e.target.value)} required autoFocus />
      </Campo>
      <Campo rotulo="Tipo">
        <select value={tipo} onChange={(e) => setTipo(e.target.value as Orcamento["tipo"])}>
          {Object.entries(TIPOS_DE_ORCAMENTO).map(([v, r]) => <option key={v} value={v}>{r}</option>)}
        </select>
      </Campo>
    </Formulario>
  );
}

function FormLote({ orcamento, aoTerminar }: { orcamento: Orcamento; aoTerminar: () => void }) {
  const [nome, setNome] = useState("");
  return (
    <Formulario rotulo="Criar lote" aoCancelar={aoTerminar}
      aoEnviar={async () => { await api.criar(`/api/orcamentos/${orcamento.id}/lotes`, { nome }); aoTerminar(); }}>
      <Campo rotulo="Nome do lote" ajuda="As lojas são escolhidas por lote: itens do mesmo lote vêm das mesmas 3 lojas.">
        <input value={nome} onChange={(e) => setNome(e.target.value)} required autoFocus />
      </Campo>
    </Formulario>
  );
}

function FormItem({ loteId, item, trocar, duracao, aoTerminar }: {
  loteId: string; item?: Item; trocar?: boolean; duracao: number; aoTerminar: () => void;
}) {
  const { dados: categorias } = useDados<Categoria[]>("/api/catalogos/categorias");
  const [v, setV] = useState({
    descricao: item?.descricao ?? "", categoria: item?.categoria ?? "", marca: item?.marca ?? "",
    modelo: item?.modelo ?? "", apresentacao: item?.apresentacao ?? "", ean: item?.ean ?? "",
    unidade: item?.unidade ?? "un", qtd_planejada: String(item?.qtd_planejada ?? ""),
    mes_inicio: String(item?.mes_inicio ?? 1), mes_fim: String(item?.mes_fim ?? duracao),
    margem_min_percentual: item?.margem_min_percentual?.toString() ?? "",
    margem_max_percentual: item?.margem_max_percentual?.toString() ?? "", travado: item?.travado ?? false,
    justificativa: "",
  });
  const mudar = (campo: keyof typeof v) => (e: { target: { value: string } }) => setV({ ...v, [campo]: e.target.value });
  const atributos = categorias?.find((c) => c.id === v.categoria)?.atributos ?? [];

  async function enviar() {
    const corpo = {
      descricao: v.descricao, categoria: v.categoria || null, marca: v.marca || null, modelo: v.modelo || null,
      apresentacao: v.apresentacao || null, ean: v.ean || null, unidade: v.unidade || "un",
      qtd_planejada: Number(v.qtd_planejada), mes_inicio: Number(v.mes_inicio), mes_fim: Number(v.mes_fim),
      margem_min_percentual: numeroOuNulo(v.margem_min_percentual),
      margem_max_percentual: numeroOuNulo(v.margem_max_percentual), travado: v.travado,
    };
    if (trocar && item) await api.criar(`/api/itens/${item.id}/trocar-produto`, { ...corpo, justificativa: v.justificativa });
    else if (item) await api.mudar(`/api/itens/${item.id}`, corpo);
    else await api.criar(`/api/lotes/${loteId}/itens`, corpo);
    aoTerminar();
  }

  return (
    <Formulario rotulo={trocar ? "Trocar produto" : item ? "Salvar" : "Adicionar item"} aoEnviar={enviar} aoCancelar={aoTerminar}>
      {trocar && <p className="explicacao">O item atual sai do orçamento e fica no histórico, com as pesquisas. O produto novo precisa ser pesquisado nas lojas (Saída 1).</p>}
      <Campo rotulo="Descrição" ajuda="Como o produto é chamado, ex.: Papel sulfite A4 75 g">
        <input value={v.descricao} onChange={mudar("descricao")} required autoFocus />
      </Campo>
      <div className="linha-campos">
        <Campo rotulo="Categoria" ajuda="define os atributos conferidos">
          <select value={v.categoria} onChange={mudar("categoria")}>
            <option value="">—</option>
            {categorias?.map((c) => <option key={c.id} value={c.id}>{c.id}</option>)}
          </select>
        </Campo>
        <Campo rotulo="Marca" ajuda="obrigatória para o 🟢 (D-17)"><input value={v.marca} onChange={mudar("marca")} /></Campo>
        <Campo rotulo="Modelo" ajuda="se houver"><input value={v.modelo} onChange={mudar("modelo")} /></Campo>
      </div>
      <div className="linha-campos">
        <Campo rotulo="Apresentação" ajuda="ex.: pacote com 500 folhas"><input value={v.apresentacao} onChange={mudar("apresentacao")} /></Campo>
        <Campo rotulo="Código de barras (EAN)" ajuda="se souber: dá 🟢 direto"><input value={v.ean} onChange={mudar("ean")} inputMode="numeric" /></Campo>
        <Campo rotulo="Unidade"><input value={v.unidade} onChange={mudar("unidade")} /></Campo>
      </div>
      {atributos.length > 0 && <p className="discreto pequeno">Nesta categoria o sistema confere: {atributos.join(", ")}. Escreva-os na descrição ou na apresentação.</p>}
      <div className="linha-campos">
        <Campo rotulo="Quantidade por mês"><input type="number" min={0} value={v.qtd_planejada} onChange={mudar("qtd_planejada")} required /></Campo>
        <Campo rotulo="Do mês"><input type="number" min={1} max={duracao} value={v.mes_inicio} onChange={mudar("mes_inicio")} required /></Campo>
        <Campo rotulo="Até o mês"><input type="number" min={1} max={duracao} value={v.mes_fim} onChange={mudar("mes_fim")} required /></Campo>
      </div>
      <details>
        <summary>Margem de ajuste para fechar o teto</summary>
        <div className="linha-campos">
          <Campo rotulo="Pode baixar até (%)" ajuda="padrão −20"><input type="number" min={-100} max={0} value={v.margem_min_percentual} onChange={mudar("margem_min_percentual")} placeholder="-20" /></Campo>
          <Campo rotulo="Pode subir até (%)" ajuda="padrão +20"><input type="number" min={0} max={1000} value={v.margem_max_percentual} onChange={mudar("margem_max_percentual")} placeholder="20" /></Campo>
          <label className="marcador"><input type="checkbox" checked={v.travado} onChange={(e) => setV({ ...v, travado: e.target.checked })} /> travar a quantidade</label>
        </div>
      </details>
      {trocar && <Campo rotulo="Motivo da troca"><textarea rows={2} value={v.justificativa} onChange={mudar("justificativa")} required /></Campo>}
    </Formulario>
  );
}

function FormCargo({ orcamentoId, cargo, duracao, aoTerminar }: { orcamentoId: string; cargo?: Cargo; duracao: number; aoTerminar: () => void }) {
  const { dados: jornadas } = useDados<Jornada[]>("/api/catalogos/jornadas");
  const [v, setV] = useState({
    nome: cargo?.nome ?? "", regime: cargo?.regime ?? "recibo", jornada_id: cargo?.jornada_id ?? "regra_geral",
    horas: cargo ? horas(cargo.horas_planejadas_centesimos) : "", postos: String(cargo?.postos ?? 1),
    mes_inicio: String(cargo?.mes_inicio ?? 1), mes_fim: String(cargo?.mes_fim ?? duracao),
    margem_min_percentual: cargo?.margem_min_percentual?.toString() ?? "",
    margem_max_percentual: cargo?.margem_max_percentual?.toString() ?? "", travado: cargo?.travado ?? false,
  });
  const mudar = (campo: keyof typeof v) => (e: { target: { value: string } }) => setV({ ...v, [campo]: e.target.value });
  const jornada = jornadas?.find((j) => j.id === v.jornada_id);

  async function enviar() {
    const horas_planejadas_centesimos = centesimosDeTexto(v.horas);
    if (!horas_planejadas_centesimos) throw new Error("Informe as horas por mês, por exemplo 80 ou 91,5.");
    const corpo = {
      nome: v.nome, regime: v.regime, jornada_id: v.jornada_id, horas_planejadas_centesimos, postos: Number(v.postos),
      mes_inicio: Number(v.mes_inicio), mes_fim: Number(v.mes_fim),
      margem_min_percentual: numeroOuNulo(v.margem_min_percentual),
      margem_max_percentual: numeroOuNulo(v.margem_max_percentual), travado: v.travado,
    };
    if (cargo) await api.mudar(`/api/cargos/${cargo.id}`, corpo);
    else await api.criar(`/api/orcamentos/${orcamentoId}/cargos`, corpo);
    aoTerminar();
  }

  return (
    <Formulario rotulo={cargo ? "Salvar" : "Adicionar cargo"} aoEnviar={enviar} aoCancelar={aoTerminar}>
      <div className="linha-campos">
        <Campo rotulo="Cargo"><input value={v.nome} onChange={mudar("nome")} required autoFocus /></Campo>
        <Campo rotulo="Regime" ajuda="MEI, se a ocupação permitir; senão Recibo (D-45)">
          <select value={v.regime} onChange={mudar("regime")}>
            {Object.entries(REGIMES).map(([k, r]) => <option key={k} value={k}>{r}</option>)}
          </select>
        </Campo>
      </div>
      <Campo rotulo="Jornada legal do cargo" ajuda={jornada ? `${jornada.semanal_horas} h semanais · divisor ${jornada.divisor} · ${jornada.fonte_legal}` : undefined}>
        <select value={v.jornada_id} onChange={mudar("jornada_id")}>
          {jornadas?.map((j) => <option key={j.id} value={j.id}>{j.descricao}</option>)}
        </select>
      </Campo>
      <div className="linha-campos">
        <Campo rotulo="Horas por mês" ajuda="pode ter decimais, ex.: 91,5"><input value={v.horas} onChange={mudar("horas")} required inputMode="decimal" /></Campo>
        <Campo rotulo="Postos"><input type="number" min={1} value={v.postos} onChange={mudar("postos")} required /></Campo>
        <Campo rotulo="Do mês"><input type="number" min={1} max={duracao} value={v.mes_inicio} onChange={mudar("mes_inicio")} required /></Campo>
        <Campo rotulo="Até o mês"><input type="number" min={1} max={duracao} value={v.mes_fim} onChange={mudar("mes_fim")} required /></Campo>
      </div>
      <details>
        <summary>Margem de ajuste das horas para fechar o teto</summary>
        <div className="linha-campos">
          <Campo rotulo="Pode baixar até (%)"><input type="number" min={-100} max={0} value={v.margem_min_percentual} onChange={mudar("margem_min_percentual")} placeholder="-20" /></Campo>
          <Campo rotulo="Pode subir até (%)" ajuda="nunca passa da jornada legal"><input type="number" min={0} max={1000} value={v.margem_max_percentual} onChange={mudar("margem_max_percentual")} placeholder="20" /></Campo>
          <label className="marcador"><input type="checkbox" checked={v.travado} onChange={(e) => setV({ ...v, travado: e.target.checked })} /> travar as horas</label>
        </div>
      </details>
    </Formulario>
  );
}

export function AbaCadastro({ projeto, atualizar }: PropsDaAba) {
  const [janela, setJanela] = useState<Janela | null>(null);
  const fechar = () => { setJanela(null); atualizar(); };
  const orcamentos = projeto.orcamentos ?? [];
  const excluir = (rota: string, id: string) => async () => { await api.criar(`/api/${rota}/${id}/excluir`); atualizar(); };

  return (
    <div>
      <div className="cabecalho-secao">
        <p className="discreto">Cada orçamento é uma rubrica do projeto. Nada é apagado de verdade: o que for excluído continua no histórico.</p>
        <button onClick={() => setJanela({ tipo: "orcamento" })}>+ Orçamento (rubrica)</button>
      </div>
      {orcamentos.length === 0 && <div className="vazio"><p>Comece criando um orçamento, por exemplo "Material pedagógico" (materiais) ou "Recursos humanos" (mão de obra).</p></div>}
      {orcamentos.map((o) => (
        <div key={o.id} className="bloco">
          <div className="cabecalho-secao">
            <h2>{o.nome} <span className="discreto">· {TIPOS_DE_ORCAMENTO[o.tipo]}</span></h2>
            <div className="botoes">
              {o.tipo !== "mao_de_obra" && <button className="secundario" onClick={() => setJanela({ tipo: "lote", orcamento: o })}>+ Lote</button>}
              {o.tipo === "mao_de_obra" && <button className="secundario" onClick={() => setJanela({ tipo: "cargo", orcamentoId: o.id })}>+ Cargo</button>}
              <BotaoAcao classe="perigo pequeno" aoClicar={excluir("orcamentos", o.id)} confirmar={`Excluir o orçamento "${o.nome}"?`}>Excluir</BotaoAcao>
            </div>
          </div>
          {o.lotes.map((l) => (
            <div key={l.id} className="lote">
              <div className="cabecalho-secao">
                <h3>Lote {l.nome}</h3>
                <div className="botoes">
                  <button className="secundario pequeno" onClick={() => setJanela({ tipo: "item", loteId: l.id })}>+ Item</button>
                  <BotaoAcao classe="perigo pequeno" aoClicar={excluir("lotes", l.id)} confirmar={`Excluir o lote "${l.nome}"?`}>Excluir lote</BotaoAcao>
                </div>
              </div>
              {l.itens.length === 0 ? <p className="discreto">Nenhum item.</p> : (
                <table className="tabela">
                  <thead><tr><th>Item</th><th>Marca</th><th>Categoria</th><th className="n">Qtd./mês</th><th>Meses</th><th>EAN</th><th /></tr></thead>
                  <tbody>
                    {l.itens.map((i) => (
                      <tr key={i.id}>
                        <td>{i.descricao}{i.apresentacao ? <div className="discreto pequeno">{i.apresentacao}</div> : null}</td>
                        <td>{i.marca ?? <span className="atencao">definir</span>}</td>
                        <td>{i.categoria ?? "—"}</td>
                        <td className="n">{i.qtd_planejada} {i.unidade}{i.travado ? " 🔒" : ""}</td>
                        <td>{i.mes_inicio}–{i.mes_fim}</td>
                        <td className="pequeno">{i.ean ?? "—"}</td>
                        <td className="botoes">
                          <button className="link" onClick={() => setJanela({ tipo: "item", loteId: l.id, item: i })}>editar</button>
                          <button className="link" onClick={() => setJanela({ tipo: "item", loteId: l.id, item: i, trocar: true })}>trocar produto</button>
                          <BotaoAcao classe="link perigo" aoClicar={excluir("itens", i.id)} confirmar={`Excluir "${i.descricao}"?`}>excluir</BotaoAcao>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          ))}
          {o.tipo === "mao_de_obra" && (o.cargos.length === 0 ? <p className="discreto">Nenhum cargo.</p> : (
            <table className="tabela">
              <thead><tr><th>Cargo</th><th>Regime</th><th className="n">Horas/mês</th><th className="n">Postos</th><th>Meses</th><th /></tr></thead>
              <tbody>
                {o.cargos.map((c) => (
                  <tr key={c.id}>
                    <td>{c.nome}</td><td>{REGIMES[c.regime]}</td>
                    <td className="n">{horas(c.horas_planejadas_centesimos)}{c.travado ? " 🔒" : ""}</td>
                    <td className="n">{c.postos}</td><td>{c.mes_inicio}–{c.mes_fim}</td>
                    <td className="botoes">
                      <button className="link" onClick={() => setJanela({ tipo: "cargo", orcamentoId: o.id, cargo: c })}>editar</button>
                      <BotaoAcao classe="link perigo" aoClicar={excluir("cargos", c.id)} confirmar={`Excluir "${c.nome}"?`}>excluir</BotaoAcao>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ))}
        </div>
      ))}

      {janela?.tipo === "orcamento" && <Modal titulo="Novo orçamento" aoFechar={fechar}><FormOrcamento projetoId={projeto.id} aoTerminar={fechar} /></Modal>}
      {janela?.tipo === "lote" && <Modal titulo={`Novo lote em ${janela.orcamento.nome}`} aoFechar={fechar}><FormLote orcamento={janela.orcamento} aoTerminar={fechar} /></Modal>}
      {janela?.tipo === "item" && (
        <Modal titulo={janela.trocar ? "Trocar produto" : janela.item ? "Editar item" : "Novo item"} aoFechar={fechar}>
          <FormItem loteId={janela.loteId} item={janela.item} trocar={janela.trocar} duracao={projeto.duracao_meses} aoTerminar={fechar} />
        </Modal>
      )}
      {janela?.tipo === "cargo" && (
        <Modal titulo={janela.cargo ? "Editar cargo" : "Novo cargo"} aoFechar={fechar}>
          <FormCargo orcamentoId={janela.orcamentoId} cargo={janela.cargo} duracao={projeto.duracao_meses} aoTerminar={fechar} />
        </Modal>
      )}
    </div>
  );
}
