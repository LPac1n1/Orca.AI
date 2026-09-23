// Formatos brasileiros. Dinheiro chega e sai em centavos inteiros: nada de conta com número decimal.

export function reais(centavos: number | null | undefined): string {
  if (centavos === null || centavos === undefined) return "—";
  const sinal = centavos < 0 ? "-" : "";
  const abs = Math.abs(centavos);
  const inteiro = Math.floor(abs / 100).toString().replace(/\B(?=(\d{3})+(?!\d))/g, ".");
  return `${sinal}R$ ${inteiro},${String(abs % 100).padStart(2, "0")}`;
}

/** "1.234,56", "R$ 1234,5", "12" → centavos. Devolve null se não for um valor válido. */
export function centavosDeTexto(texto: string): number | null {
  const limpo = texto.replace(/R\$|\s/g, "");
  const m = /^(\d{1,3}(?:\.\d{3})+|\d+)(?:,(\d{1,2}))?$/.exec(limpo);
  if (!m) return null;
  return Number(m[1].replace(/\./g, "")) * 100 + Number((m[2] ?? "0").padEnd(2, "0"));
}

export function textoDeCentavos(centavos: number | null | undefined): string {
  return centavos === null || centavos === undefined ? "" : reais(centavos).replace("R$ ", "");
}

/** Horas em centésimos: 9150 → "91,50". */
export function horas(centesimos: number | null | undefined): string {
  if (centesimos === null || centesimos === undefined) return "—";
  return `${Math.floor(centesimos / 100)},${String(centesimos % 100).padStart(2, "0")}`;
}

/** "91,5" ou "91" → 9150. */
export function centesimosDeTexto(texto: string): number | null {
  const m = /^(\d+)(?:,(\d{1,2}))?$/.exec(texto.trim());
  if (!m) return null;
  return Number(m[1]) * 100 + Number((m[2] ?? "0").padEnd(2, "0"));
}

export function cnpj(valor: string | null | undefined): string {
  if (!valor) return "sem CNPJ";
  const v = valor.toUpperCase();
  return v.length === 14 ? `${v.slice(0, 2)}.${v.slice(2, 5)}.${v.slice(5, 8)}/${v.slice(8, 12)}-${v.slice(12)}` : v;
}

const BRASILIA: Intl.DateTimeFormatOptions = { timeZone: "America/Sao_Paulo" };

export function dataHora(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("pt-BR", { ...BRASILIA, dateStyle: "short", timeStyle: "short" });
}

export function data(iso: string | null | undefined): string {
  if (!iso) return "—";
  const [a, m, d] = iso.slice(0, 10).split("-");
  return `${d}/${m}/${a}`;
}

export function tamanho(bytes: number): string {
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1).replace(".", ",")} MB`;
}

export const TIPOS_DE_ORCAMENTO = { materiais: "Materiais", mao_de_obra: "Mão de obra", servicos: "Serviços" } as const;
export const REGIMES = { mei: "MEI", recibo: "Recibo (RPA)", clt: "CLT" } as const;
export const TIPOS_DE_TAREFA = {
  coletar_item: "Ler página de produto",
  coletar_cargo: "Ler página de vaga",
  captura_assistida: "Captura com janela",
  comprovante: "Comprovante da Receita",
  consultar_cnpj: "Consultar CNPJs",
  fechar_teto: "Fechar o teto",
  exportar: "Gerar documentos",
} as const;
