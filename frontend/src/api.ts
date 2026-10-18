const API_BASE = import.meta.env.VITE_API_URL ?? "";

const DEVICE_TOKEN_STORAGE_KEY = "kopi_device_token";
let fetchInterceptorInstalled = false;

export function apiUrl(path: string): string {
  if (path.startsWith("http")) return path;
  return `${API_BASE}${path}`;
}

export function getDeviceToken(): string {
  try {
    return localStorage.getItem(DEVICE_TOKEN_STORAGE_KEY) ?? "";
  } catch {
    return "";
  }
}

export function setDeviceToken(token: string): void {
  try {
    localStorage.setItem(DEVICE_TOKEN_STORAGE_KEY, token);
  } catch {
    // Ignore storage errors in private browsing
  }
}

export function clearDeviceToken(): void {
  try {
    localStorage.removeItem(DEVICE_TOKEN_STORAGE_KEY);
  } catch {
    // Ignore
  }
}

export function notifyPairingStateChanged(): void {
  window.dispatchEvent(new CustomEvent("kopi:pairing-check"));
}

export function installPairedFetchInterceptor(): void {
  if (fetchInterceptorInstalled || typeof window === "undefined") return;
  fetchInterceptorInstalled = true;

  const nativeFetch = window.fetch.bind(window);
  window.fetch = async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
    const urlStr = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;
    const isApiCall = urlStr.includes("/api/");

    if (!isApiCall) {
      return nativeFetch(input, init);
    }

    const headers = new Headers(init?.headers ?? (input instanceof Request ? input.headers : undefined));
    const token = getDeviceToken();
    if (token && !headers.has("X-Kopi-Device-Token")) {
      headers.set("X-Kopi-Device-Token", token);
    }

    const nextInit: RequestInit = {
      ...init,
      headers,
      credentials: init?.credentials ?? "include",
    };

    const res = await nativeFetch(input, nextInit);
    if (
      res.status === 403 &&
      !urlStr.includes("/api/admin/") &&
      !urlStr.includes("/api/pair/")
    ) {
      notifyPairingStateChanged();
    }
    return res;
  };
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
