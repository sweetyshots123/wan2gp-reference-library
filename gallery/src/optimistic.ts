// 1.9.7: borrado optimista. La app registra cómo quitar elementos de la lista cargada (y cómo devolverlos);
// el borrado los quita al instante y, si el servidor falla, los devuelve con un aviso de error.
type Remover = (hashes: Set<string>) => () => void;
let remover: Remover | null = null;
export const setRemover = (r: Remover | null) => { remover = r; };
export const removeLocal = (hashes: string[]): (() => void) => (remover ? remover(new Set(hashes)) : () => {});
