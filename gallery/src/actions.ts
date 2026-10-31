import { call, Resp } from "./api";
import { toast } from "./ui";

// acciones compartidas con deshacer por token (1.8.6)
const UNDO: Record<string, string> = { tag_delete: "tag_undo_delete", col_delete: "col_undo_delete", v_delete: "v_undo_delete", person_delete: "person_undo_delete" };

// Ejecuta una acción de la Media Library, muestra su mensaje y ofrece "Deshacer" cuando el servidor da un token.
export async function act(action: string, body: Record<string, any>, after: () => void, opts: { quiet?: boolean } = {}): Promise<Resp | null> {
  try {
    const r = await call(action, body);
    const msg = r.toast || r.message || r.error;
    if (!r.ok && r.code === "faces_busy") toast(msg || "Agrupando caras: inténtalo en unos segundos", "info");   // 1.10.0
    else if (!r.ok) toast(msg || "Error", "err");
    else if (r.undo_remove) toast(msg || "Hecho", "ok", { label: "Deshacer", run: () => act("undo_remove", { token: r.undo_remove }, after) });
    else if (r.undo_token && UNDO[action]) toast(msg || "Hecho", "ok", { label: "Deshacer", run: () => act(UNDO[action], { undo_token: r.undo_token }, after) });
    else if (r.undo_forget) toast(msg || "Hecho", r.kind === "warn" ? "err" : "ok", { label: "Deshacer", run: () => act("forget_undo", { token: r.undo_forget }, after) });
    else if (msg && !opts.quiet) toast(msg, r.kind === "info" ? "info" : "ok");
    after();
    return r;
  } catch (e: any) {
    toast(`Error: ${e?.message || e}`, "err");
    return null;
  }
}
