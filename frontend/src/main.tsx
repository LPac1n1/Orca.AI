import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { HashRouter, Link, Route, Routes } from "react-router-dom";
import { useDados } from "./ganchos";
import { PaginaCatalogos } from "./paginas/Catalogos";
import { PaginaProjeto } from "./paginas/Projeto";
import { PaginaProjetos } from "./paginas/Projetos";
import type { Situacao } from "./tipos";
import "./estilos.css";

function Topo() {
  const { dados } = useDados<Situacao>("/api/situacao");
  return (
    <header className="topo">
      <Link to="/" className="marca">Orça.AI</Link>
      <span className="discreto">montador de orçamentos para OSCs</span>
      <span className="espaco" />
      <Link to="/catalogos">Catálogos</Link>
      {dados && <span className="usuario" title={`Pasta de dados: ${dados.pasta_dados}`}>{dados.usuario}</span>}
    </header>
  );
}

function App() {
  return (
    <HashRouter>
      <Topo />
      <main className="conteudo">
        <Routes>
          <Route path="/" element={<PaginaProjetos />} />
          <Route path="/projetos/:id/*" element={<PaginaProjeto />} />
          <Route path="/catalogos" element={<PaginaCatalogos />} />
          <Route path="/catalogos/:id" element={<PaginaCatalogos />} />
        </Routes>
      </main>
    </HashRouter>
  );
}

createRoot(document.getElementById("raiz")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
