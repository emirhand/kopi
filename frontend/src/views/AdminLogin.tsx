import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { apiUrl, parseErrorDetail } from "../api";
import { Keypad } from "../components/Keypad";
import { KioskButton } from "../components/KioskButton";
import { StatusModal } from "../components/StatusModal";

const SESSION_KEY = "kopi_admin_password";

export function AdminLogin() {
  const nav = useNavigate();
  const [pin, setPin] = useState("");
  const [busy, setBusy] = useState(false);
  const [modal, setModal] = useState<{ title: string; message: string } | null>(null);

  function maskDisplay(value: string) {
    return value ? "●".repeat(value.length) : "Enter PIN";
  }

  async function submit() {
    if (!pin) return;
    setBusy(true);
    try {
      const res = await fetch(apiUrl("/api/admin/verify"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ password: pin }),
      });
      if (!res.ok) {
        setModal({ title: "Admin", message: await parseErrorDetail(res) });
        return;
      }
      const data = await res.json();
      if (!data.valid) {
        setModal({ title: "Admin", message: "Invalid PIN." });
        setPin("");
        return;
      }
      sessionStorage.setItem(SESSION_KEY, pin);
      setPin("");
      nav("/admin/panel");
    } catch (e) {
      setModal({
        title: "Admin",
        message: e instanceof Error ? e.message : "Network error",
      });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="h-full flex flex-col bg-kiosk-bg p-4 gap-4">
      <div className="shrink-0 flex items-center gap-3">
        <KioskButton variant="ghost" className="min-h-[3.5rem] px-5 text-lg" onClick={() => nav("/")}>
          ← Back
        </KioskButton>
        <h2 className="text-2xl font-bold">Admin</h2>
      </div>

      <div
        className="shrink-0 rounded-2xl border-2 border-white/20 bg-kiosk-panel px-4 py-5 text-center text-2xl font-mono tracking-widest text-kiosk-text"
        aria-live="polite"
      >
        {maskDisplay(pin)}
      </div>

      <Keypad
        className="flex-1 min-h-0"
        onDigit={(d) => setPin((p) => (p.length < 32 ? p + d : p))}
        onBackspace={() => setPin((p) => p.slice(0, -1))}
        onClear={() => setPin("")}
      />

      <KioskButton variant="primary" className="shrink-0 w-full text-2xl" disabled={busy} onClick={submit}>
        {busy ? "Checking…" : "Unlock"}
      </KioskButton>

      <StatusModal
        open={!!modal}
        title={modal?.title ?? ""}
        message={modal?.message ?? ""}
        variant="error"
        onClose={() => setModal(null)}
      />
    </div>
  );
}

export function getAdminPassword(): string | null {
  return sessionStorage.getItem(SESSION_KEY);
}

export function clearAdminSession() {
  sessionStorage.removeItem(SESSION_KEY);
}
