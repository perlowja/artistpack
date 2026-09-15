/** Tiny className joiner. Avoids pulling in clsx for what is two lines. */
export function cx(...parts: Array<string | false | null | undefined>): string {
  let out = "";
  for (const p of parts) {
    if (!p) continue;
    if (out) out += " ";
    out += p;
  }
  return out;
}