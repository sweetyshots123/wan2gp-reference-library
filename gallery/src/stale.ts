// 1.12.14: an open Galería tab keeps running its old JS after WanGP restarts; the server answers queries with its
// version (r.v). The bar is shown once per server version (closing it remembers that version) and speaks EN/ES.
export const STALE_KEY = "gal.staleSeen";
export function staleShow(serverV: unknown, build: string, seen: string | null): boolean {
  if (!serverV || !build) return false;
  const v = String(serverV);
  return v !== build && v !== seen;
}
export function staleText(lang: string, build: string, server: string) {
  const es = String(lang || "").toLowerCase().startsWith("es");
  return es
    ? { msg: `Esta pestaña de la Galería es la ${build} y el servidor ya usa la ${server}.`, reload: "Recargar", close: "Cerrar" }
    : { msg: `This Galería tab runs ${build}; the server already runs ${server}.`, reload: "Reload", close: "Close" };
}
