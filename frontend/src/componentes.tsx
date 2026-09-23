import { useState, type FormEvent, type ReactNode } from "react";
import type { Status } from "./tipos";

export function Selo({ status, texto }: { status: Status | null; texto?: string }) {
  if (!status) return <span className="selo neutro">{texto ?? "—"}</span>;
  const rotulo = { verde: "pronto", amarelo: "revisar", vermelho: "problema" }[status];
  return <span className={`selo ${status}`}>{texto ?? rotulo}</span>;
}

export function Aviso({ tipo = "info", children }: { tipo?: "info" | "erro" | "ok" | "atencao"; children: ReactNode }) {
  return <div className={`aviso ${tipo}`}>{children}</div>;
}

export function Carregando() {
  return <p className="discreto">Carregando…</p>;
}

export function Modal({ titulo, aoFechar, children }: { titulo: string; aoFechar: () => void; children: ReactNode }) {
  return (
    <div className="fundo-modal" onMouseDown={(e) => e.target === e.currentTarget && aoFechar()}>
      <div className="modal" role="dialog" aria-modal="true" aria-label={titulo}>
        <div className="modal-topo">
          <h2>{titulo}</h2>
          <button className="fechar" onClick={aoFechar} aria-label="Fechar">×</button>
        </div>
        {children}
      </div>
    </div>
  );
}

/** Formulário com botão de enviar, mensagem de erro e estado "salvando". */
export function Formulario({
  aoEnviar,
  rotulo = "Salvar",
  children,
  aoCancelar,
}: {
  aoEnviar: () => Promise<unknown>;
  rotulo?: string;
  children: ReactNode;
  aoCancelar?: () => void;
}) {
  const [erro, setErro] = useState<string | null>(null);
  const [salvando, setSalvando] = useState(false);
  async function enviar(e: FormEvent) {
    e.preventDefault();
    setSalvando(true);
    setErro(null);
    try {
      await aoEnviar();
    } catch (err) {
      setErro((err as Error).message);
    } finally {
      setSalvando(false);
    }
  }
  return (
    <form onSubmit={enviar} className="formulario">
      {children}
      {erro && <Aviso tipo="erro">{erro}</Aviso>}
      <div className="acoes">
        {aoCancelar && <button type="button" className="secundario" onClick={aoCancelar}>Cancelar</button>}
        <button type="submit" disabled={salvando}>{salvando ? "Salvando…" : rotulo}</button>
      </div>
    </form>
  );
}

export function Campo({
  rotulo,
  ajuda,
  children,
}: {
  rotulo: string;
  ajuda?: string;
  children: ReactNode;
}) {
  return (
    <label className="campo">
      <span className="rotulo">{rotulo}</span>
      {children}
      {ajuda && <span className="ajuda">{ajuda}</span>}
    </label>
  );
}

/** Botão que executa uma ação na API e mostra o erro, se houver. */
export function BotaoAcao({
  aoClicar,
  children,
  classe = "",
  confirmar,
  titulo,
}: {
  aoClicar: () => Promise<unknown>;
  children: ReactNode;
  classe?: string;
  confirmar?: string;
  titulo?: string;
}) {
  const [ocupado, setOcupado] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  async function clicar() {
    if (confirmar && !window.confirm(confirmar)) return;
    setOcupado(true);
    setErro(null);
    try {
      await aoClicar();
    } catch (e) {
      setErro((e as Error).message);
    } finally {
      setOcupado(false);
    }
  }
  return (
    <span className="botao-acao">
      <button className={classe} onClick={clicar} disabled={ocupado} title={titulo}>
        {ocupado ? "Aguarde…" : children}
      </button>
      {erro && <span className="erro-curto" role="alert">{erro}</span>}
    </span>
  );
}

interface PedidoDeDecisao {
  titulo: string;
  explicacao: ReactNode;
  rotulo: string;
  sugestao?: string;
  aoConfirmar: (justificativa: string) => Promise<unknown>;
}

/** Janela que pede a justificativa de uma decisão (as decisões ficam no histórico, com o seu nome). */
export function useDecisao(): [ReactNode, (pedido: PedidoDeDecisao) => void] {
  const [pedido, setPedido] = useState<PedidoDeDecisao | null>(null);
  const [texto, setTexto] = useState("");
  const abrir = (p: PedidoDeDecisao) => {
    setTexto(p.sugestao ?? "");
    setPedido(p);
  };
  const janela = pedido && (
    <Modal titulo={pedido.titulo} aoFechar={() => setPedido(null)}>
      <div className="explicacao">{pedido.explicacao}</div>
      <Formulario
        rotulo={pedido.rotulo}
        aoCancelar={() => setPedido(null)}
        aoEnviar={async () => {
          if (!texto.trim()) throw new Error("Escreva o motivo da decisão.");
          await pedido.aoConfirmar(texto.trim());
          setPedido(null);
        }}
      >
        <Campo rotulo="Motivo" ajuda="Fica registrado no histórico, com o seu nome, a data e a hora.">
          <textarea value={texto} onChange={(e) => setTexto(e.target.value)} rows={3} autoFocus />
        </Campo>
      </Formulario>
    </Modal>
  );
  return [janela, abrir];
}
