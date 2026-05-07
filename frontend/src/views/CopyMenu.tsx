import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { apiUrl, parseErrorDetail } from "../api";
import { KioskButton } from "../components/KioskButton";
import { StatusModal } from "../components/StatusModal";

export function CopyMenu() {
  const nav = useNavigate();
  const [duplex, setDuplex] = useState(false);
  const [busy, setBusy] = useState(false);
  const [modal, setModal] = useState<{ title: string; message: string; variant: "info" | "error" } | null>(
    null,
  );

  async function runCopy() {
    setBusy(true);
    try {
      const res = await fetch(apiUrl("/api/copy"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ duplex }),
      });
      if (!res.ok) {
        const msg = await parseErrorDetail(res);
        setModal({ title: "Copy", message: msg, variant: "error" });
        return;
      }
      setModal({ title: "Copy", message: "Copy job submitted.", variant: "info" });
    } catch (e) {
      setModal({
        title: "Copy",
        message: e instanceof Error ? e.message : "Network error",
        variant: "error",
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
        <h2 className="text-2xl font-bold">Copy</h2>
      </div>

      <KioskButton
        variant={duplex ? "primary" : "secondary"}
        className="shrink-0 w-full text-2xl"
        onClick={() => setDuplex((v) => !v)}
      >
        Duplex: {duplex ? "On" : "Off"}
      </KioskButton>

      <KioskButton
        variant="primary"
        className="flex-1 min-h-0 w-full text-3xl md:text-4xl font-black"
        disabled={busy}
        onClick={runCopy}
      >
        {busy ? "Working…" : "Start Copy"}
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
