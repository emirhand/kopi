import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { apiUrl, parseErrorDetail } from "../api";
import { KioskButton } from "../components/KioskButton";
import { StatusModal } from "../components/StatusModal";
import { clearAdminSession, getAdminPassword } from "./AdminLogin";

type Smtp = {
  host: string;
  port: number;
  user: string;
  password: string;
  from_email: string;
  tls: boolean;
};

const emptySmtp: Smtp = {
  host: "",
  port: 587,
  user: "",
  password: "",
  from_email: "",
  tls: true,
};

export function AdminPanel() {
  const nav = useNavigate();
  const [smtp, setSmtp] = useState<Smtp>(emptySmtp);
  const [loaded, setLoaded] = useState(false);
  const [busy, setBusy] = useState(false);
  const [modal, setModal] = useState<{ title: string; message: string; variant: "info" | "error" } | null>(
    null,
  );

  useEffect(() => {
    const pw = getAdminPassword();
    if (!pw) {
      nav("/admin", { replace: true });
      return;
    }

    (async () => {
      try {
        const res = await fetch(apiUrl("/api/admin/settings"), {
          headers: { "X-Admin-Password": pw },
        });
        if (res.status === 401 || res.status === 403) {
          clearAdminSession();
          nav("/admin", { replace: true });
          return;
        }
        if (!res.ok) {
          setModal({ title: "Settings", message: await parseErrorDetail(res), variant: "error" });
          return;
        }
        const data = await res.json();
        setSmtp({ ...emptySmtp, ...data.smtp });
      } catch (e) {
        setModal({
          title: "Settings",
          message: e instanceof Error ? e.message : "Network error",
          variant: "error",
        });
      } finally {
        setLoaded(true);
      }
    })();
  }, [nav]);

  async function save() {
    const pw = getAdminPassword();
    if (!pw) {
      nav("/admin", { replace: true });
      return;
    }
    setBusy(true);
    try {
      const res = await fetch(apiUrl("/api/admin/settings"), {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
          "X-Admin-Password": pw,
        },
        body: JSON.stringify({ smtp }),
      });
      if (!res.ok) {
        setModal({ title: "Save", message: await parseErrorDetail(res), variant: "error" });
        return;
      }
      setModal({ title: "Save", message: "Settings saved.", variant: "info" });
    } catch (e) {
      setModal({
        title: "Save",
        message: e instanceof Error ? e.message : "Network error",
        variant: "error",
      });
    } finally {
      setBusy(false);
    }
  }

  function logout() {
    clearAdminSession();
    nav("/");
  }

  if (!loaded) {
    return (
      <div className="h-full flex items-center justify-center bg-kiosk-bg text-kiosk-muted text-xl">
        Loading…
      </div>
    );
  }

  const field =
    "w-full rounded-2xl border-2 border-white/20 bg-kiosk-panel px-4 py-3 text-lg text-kiosk-text outline-none focus:border-kiosk-accent";

  return (
    <div className="h-full flex flex-col bg-kiosk-bg p-4 gap-3 overflow-hidden">
      <div className="shrink-0 flex items-center gap-2">
        <KioskButton variant="ghost" className="min-h-[3rem] px-4 text-base" onClick={() => nav("/")}>
          Home
        </KioskButton>
        <h2 className="text-xl font-bold flex-1">SMTP</h2>
        <KioskButton variant="secondary" className="min-h-[3rem] px-4 text-base" onClick={logout}>
          Log out
        </KioskButton>
      </div>

      <div className="flex-1 min-h-0 grid grid-cols-1 gap-2 content-start">
        <label className="text-sm text-kiosk-muted">
          Server
          <input
            className={`${field} mt-1`}
            value={smtp.host}
            onChange={(e) => setSmtp((s) => ({ ...s, host: e.target.value }))}
            autoComplete="off"
          />
        </label>
        <label className="text-sm text-kiosk-muted">
          Port
          <input
            className={`${field} mt-1`}
            type="number"
            inputMode="numeric"
            value={smtp.port}
            onChange={(e) => setSmtp((s) => ({ ...s, port: Number(e.target.value) || 0 }))}
          />
        </label>
        <label className="text-sm text-kiosk-muted">
          User
          <input
            className={`${field} mt-1`}
            value={smtp.user}
            onChange={(e) => setSmtp((s) => ({ ...s, user: e.target.value }))}
            autoComplete="username"
          />
        </label>
        <label className="text-sm text-kiosk-muted">
          Password
          <input
            className={`${field} mt-1`}
            type="password"
            value={smtp.password}
            onChange={(e) => setSmtp((s) => ({ ...s, password: e.target.value }))}
            autoComplete="new-password"
          />
        </label>
        <label className="text-sm text-kiosk-muted">
          From
          <input
            className={`${field} mt-1`}
            type="email"
            value={smtp.from_email}
            onChange={(e) => setSmtp((s) => ({ ...s, from_email: e.target.value }))}
          />
        </label>
        <KioskButton
          variant={smtp.tls ? "primary" : "secondary"}
          className="w-full text-lg min-h-[3.5rem]"
          onClick={() => setSmtp((s) => ({ ...s, tls: !s.tls }))}
        >
          TLS: {smtp.tls ? "On" : "Off"}
        </KioskButton>
      </div>

      <KioskButton variant="primary" className="shrink-0 w-full text-2xl" disabled={busy} onClick={save}>
        {busy ? "Saving…" : "Save"}
      </KioskButton>

      <StatusModal
        open={!!modal}
        title={modal?.title ?? ""}
        message={modal?.message ?? ""}
        variant={modal?.variant}
        onClose={() => setModal(null)}
      />
    </div>
  );
}
