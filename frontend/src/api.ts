const API_BASE = import.meta.env.VITE_API_URL ?? "";

export function apiUrl(path: string): string {
  if (path.startsWith("http")) return path;
  return `${API_BASE}${path}`;
}

export async function parseErrorDetail(res: Response): Promise<string> {
  try {
    const data = await res.json();
    const d = data?.detail;
    if (typeof d === "string") return d;
    if (Array.isArray(d) && d[0]?.msg) return d.map((x: { msg: string }) => x.msg).join(", ");
    return res.statusText || "Request failed";
  } catch {
    return res.statusText || "Request failed";
  }
}
