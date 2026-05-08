import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { apiUrl, parseErrorDetail } from "../api";
import { KOPI_USB_MOUNT_STORAGE_KEY } from "../usbStorage";
import { KioskButton } from "../components/KioskButton";
import { StatusModal } from "../components/StatusModal";

export function ScanMenu() {
  const nav = useNavigate();
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState<null | "email" | "usb">(null);
  const [modal, setModal] = useState<{ title: string; message: string; variant: "info" | "error" } | null>(
    null,
  );

  async function scanEmail() {
    if (!email.trim()) {
      setModal({ title: "Scan to Email", message: "Enter an email address.", variant: "error" });
      return;
    }
    setBusy("email");
    try {
      const res = await fetch(apiUrl("/api/scan/email"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ recipient: email.trim() }),
      });
      if (!res.ok) {
        const msg = await parseErrorDetail(res);
        setModal({ title: "Scan to Email", message: msg, variant: "error" });
        return;
      }
      setModal({ title: "Scan to Email", message: "Scan emailed.", variant: "info" });
    } catch (e) {
      setModal({
        title: "Scan to Email",
        message: e instanceof Error ? e.message : "Network error",
        variant: "error",
      });
    } finally {
      setBusy(null);
    }
  }

  async function scanUsb() {
    setBusy("usb");
    try {
      let mountPath: string | null = null;
      try {
        const raw = sessionStorage.getItem(KOPI_USB_MOUNT_STORAGE_KEY);
        mountPath = raw && raw.trim() ? raw.trim() : null;
      } catch {
        mountPath = null;
      }
      const res = await fetch(apiUrl("/api/scan/usb"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mount_path: mountPath }),
      });
      if (!res.ok) {
        const msg = await parseErrorDetail(res);
        setModal({ title: "Scan to USB", message: msg, variant: "error" });
        return;
      }
      const data = await res.json();
      setModal({ title: "Scan to USB", message: data.message ?? "Saved.", variant: "info" });
    } catch (e) {
      setModal({
        title: "Scan to USB",
        message: e instanceof Error ? e.message : "Network error",
        variant: "error",
      });
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="h-full flex flex-col bg-kiosk-bg p-4 gap-3">
      <div className="shrink-0 flex items-center gap-3">
        <KioskButton variant="ghost" className="min-h-[3.5rem] px-5 text-lg" onClick={() => nav("/")}>
          ← Back
        </KioskButton>
        <h2 className="text-2xl font-bold">Scan</h2>
      </div>

      <label className="shrink-0 block">
        <span className="sr-only">Email</span>
        <input
          type="email"
          inputMode="email"
          autoComplete="email"
          placeholder="recipient@example.com"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          className="w-full rounded-2xl border-2 border-white/20 bg-kiosk-panel px-4 py-4 text-xl text-kiosk-text placeholder:text-kiosk-muted outline-none focus:border-kiosk-accent"
        />
      </label>

      <KioskButton
        variant="primary"
        className="shrink-0 w-full text-2xl min-h-[4.5rem]"
        disabled={busy !== null}
        onClick={scanEmail}
      >
        {busy === "email" ? "Scanning…" : "Scan to Email"}
      </KioskButton>

      <KioskButton
        variant="secondary"
        className="flex-1 min-h-0 w-full text-3xl font-black"
        disabled={busy !== null}
        onClick={scanUsb}
      >
        {busy === "usb" ? "Scanning…" : "Scan to USB"}
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
