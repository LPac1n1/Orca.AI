import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "./api";
import type { Tarefa } from "./tipos";

/** Carrega um endereço da API; recarrega quando `versao` muda. */
export function useDados<T>(caminho: string | null, versao = 0) {
  const [dados, setDados] = useState<T | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [carregando, setCarregando] = useState(false);
  const [local, setLocal] = useState(0);

  useEffect(() => {
    if (!caminho) return;
    let ativo = true;
    setCarregando(true);
    api
      .obter<T>(caminho)
      .then((d) => ativo && (setDados(d), setErro(null)))
      .catch((e: Error) => ativo && setErro(e.message))
      .finally(() => ativo && setCarregando(false));
    return () => {
      ativo = false;
    };
  }, [caminho, versao, local]);

  const recarregar = useCallback(() => setLocal((n) => n + 1), []);
  return { dados, erro, carregando, recarregar };
}

export const ativa = (t: Tarefa) => t.estado === "pendente" || t.estado === "rodando" || t.estado === "esperando_usuario";

/** Acompanha uma tarefa até ela terminar. */
export function useTarefa(id: string | null) {
  const [tarefa, setTarefa] = useState<Tarefa | null>(null);
  const [pulso, setPulso] = useState(0);
  useEffect(() => {
    if (!id) return;
    let ativo = true;
    api.obter<Tarefa>(`/api/tarefas/${id}`).then((t) => ativo && setTarefa(t)).catch(() => undefined);
    return () => {
      ativo = false;
    };
  }, [id, pulso]);
  const atual = tarefa && tarefa.id === id ? tarefa : null;
  const andando = !!id && (!atual || ativa(atual));
  useEffect(() => {
    if (!andando) return;
    const relogio = setInterval(() => setPulso((n) => n + 1), 1500);
    return () => clearInterval(relogio);
  }, [andando]);
  return atual;
}

/** Acompanha as tarefas do projeto; avisa quando alguma termina. */
export function useTarefas(projetoId: string, aoTerminar: () => void, versao: number) {
  const [tarefas, setTarefas] = useState<Tarefa[]>([]);
  const ativas = useRef<Set<string>>(new Set());
  const [pulso, setPulso] = useState(0);

  useEffect(() => {
    let ativo = true;
    api
      .obter<Tarefa[]>(`/api/tarefas?projeto_id=${projetoId}&limite=30`)
      .then((lista) => {
        if (!ativo) return;
        setTarefas(lista);
        const emAndamento = new Set(lista.filter(ativa).map((t) => t.id));
        const terminou = [...ativas.current].some((id) => !emAndamento.has(id));
        ativas.current = emAndamento;
        if (terminou) aoTerminar();
      })
      .catch(() => undefined);
    return () => {
      ativo = false;
    };
  }, [projetoId, pulso, versao, aoTerminar]);

  const emAndamento = tarefas.some(ativa);
  useEffect(() => {
    if (!emAndamento) return;
    const relogio = setInterval(() => setPulso((n) => n + 1), 1500);
    return () => clearInterval(relogio);
  }, [emAndamento]);

  return { tarefas, emAndamento, atualizar: () => setPulso((n) => n + 1) };
}
