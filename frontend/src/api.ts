// Comunicação com a API local. Todo pedido que muda dados leva o cabeçalho X-Orca (proteção contra CSRF).

export class ErroApi extends Error {}

async function pedir<T>(metodo: string, caminho: string, corpo?: unknown): Promise<T> {
  const formulario = corpo instanceof FormData;
  const resposta = await fetch(caminho, {
    method: metodo,
    headers: { "X-Orca": "1", ...(corpo !== undefined && !formulario ? { "Content-Type": "application/json" } : {}) },
    body: corpo === undefined ? undefined : formulario ? corpo : JSON.stringify(corpo),
  });
  const texto = await resposta.text();
  const dados = texto ? JSON.parse(texto) : null;
  if (!resposta.ok) {
    const detalhes = Array.isArray(dados?.detalhes)
      ? ": " + dados.detalhes.map((d: { loc?: unknown[]; msg?: string }) => `${(d.loc ?? []).slice(-1)}: ${(d.msg ?? "").replace(/^Value error, /, "")}`).join("; ")
      : "";
    throw new ErroApi((dados?.erro ?? `Erro ${resposta.status}`) + detalhes);
  }
  return dados as T;
}

export const api = {
  obter: <T>(caminho: string) => pedir<T>("GET", caminho),
  criar: <T>(caminho: string, corpo: unknown = {}) => pedir<T>("POST", caminho, corpo),
  mudar: <T>(caminho: string, corpo: unknown) => pedir<T>("PATCH", caminho, corpo),
  trocar: <T>(caminho: string, corpo: unknown) => pedir<T>("PUT", caminho, corpo),
  enviar: <T>(caminho: string, formulario: FormData) => pedir<T>("POST", caminho, formulario),
};

export const evidencia = (id: string, tipo: "pdf" | "png" | "mhtml" = "pdf") => `/api/evidencias/${id}/${tipo}`;
export const arquivo = (caminho: string) => `/api/arquivos/${caminho.split("/").map(encodeURIComponent).join("/")}`;
