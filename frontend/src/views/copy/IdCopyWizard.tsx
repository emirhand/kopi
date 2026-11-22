import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { apiUrl, parseErrorDetail } from "../../api";
import { KioskButton } from "../../components/KioskButton";
import { StatusModal } from "../../components/StatusModal";

type Step = "START" | "FLIP" | "PREVIEW";

const GRID_STYLE = { width: "min(96vw, calc((100dvh - 7rem) * 1.5))" };

export function IdCopyWizard() {
  const nav = useNavigate();
  const [step, setStep] = useState<Step>("START");
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [previewSrc, setPreviewSrc] = useState<string | null>(null);
  const [busy, setBusy] = useState<"front" | "back" | "print" | null>(null);
  const [modal, setModal] = useState<{ title: string; message: string; variant: "info" | "error" } | null>(
    null,
  );

  async function discardSession(sid: string | null = sessionId) {
    if (!sid) return;
    try {
      await fetch(apiUrl("/api/copy/id/discard"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: sid }),
      });
    } catch {
      /* ignore */
    }
    setSessionId(null);
    setPreviewSrc(null);
  }

  useEffect(() => {
    return () => {
      if (sessionId) {
        void fetch(apiUrl("/api/copy/id/discard"), {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ session_id: sessionId }),
        }).catch(() => undefined);
      }
    };
  }, [sessionId]);

  async function scanFront() {
    setBusy("front");
    try {
      const res = await fetch(apiUrl("/api/copy/id/front"), { method: "POST" });
      if (!res.ok) {
        setModal({ title: "ID Copy", message: await parseErrorDetail(res), variant: "error" });
        return;
      }
      const data = await res.json();
      setSessionId(String(data.session_id));
      setStep("FLIP");
    } catch (e) {
      setModal({
        title: "ID Copy",
        message: e instanceof Error ? e.message : "Network error",
        variant: "error",
      });
    } finally {
      setBusy(null);
    }
  }

  async function scanBackAndCompose() {
    if (!sessionId) return;
    setBusy("back");
    try {
      const res = await fetch(apiUrl("/api/copy/id/back"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: sessionId }),
      });
      if (!res.ok) {
        setModal({ title: "ID Copy", message: await parseErrorDetail(res), variant: "error" });
        return;
      }
      const cres = await fetch(apiUrl("/api/copy/id/compose"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: sessionId }),
      });
      if (!cres.ok) {
        setModal({ title: "ID Copy", message: await parseErrorDetail(cres), variant: "error" });
        return;
      }
      const cdata = await cres.json();
      const b64 = cdata.preview_png_base64 as string | null | undefined;
      if (b64) setPreviewSrc(`data:image/png;base64,${b64}`);
      else setPreviewSrc(null);
      setStep("PREVIEW");
    } catch (e) {
      setModal({
        title: "ID Copy",
        message: e instanceof Error ? e.message : "Network error",
        variant: "error",
      });
    } finally {
      setBusy(null);
    }
  }

  async function doPrint() {
    if (!sessionId) return;
    setBusy("print");
    try {
      const res = await fetch(apiUrl("/api/copy/id/print"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: sessionId }),
      });
      if (!res.ok) {
        setModal({ title: "Print", message: await parseErrorDetail(res), variant: "error" });
        return;
      }
      const data = await res.json();
      setSessionId(null);
      setPreviewSrc(null);
      setStep("START");
      setModal({ title: "Print", message: (data.message as string) || "Sent to printer.", variant: "info" });
    } catch (e) {
      setModal({
        title: "Print",
        message: e instanceof Error ? e.message : "Network error",
        variant: "error",
      });
    } finally {
      setBusy(null);
    }
  }

  const hardwareBusy = busy !== null;

  return (
    <div className="flex h-full min-h-0 flex-col bg-kiosk-industrial-bezel p-3 text-zinc-100 md:p-4">
      {step === "START" && (
        <div className="flex min-h-0 flex-1 flex-col items-center justify-center">
          <div className="grid min-h-0 grid-cols-3 grid-rows-2 gap-3 md:gap-4" style={GRID_STYLE}>
            <KioskButton
              layout="tile"
              variant="industrialMuted"
              className="min-h-0 min-w-0"
              disabled={hardwareBusy}
              onClick={() => {
                void discardSession();
                nav("/copy");
              }}
            >
              ← Back
            </KioskButton>
            <div className="col-span-2 flex flex-col justify-center rounded-2xl border border-kiosk-industrial-border bg-kiosk-industrial-navy p-4">
              <p className="text-sm font-bold uppercase tracking-wider text-zinc-400">ID Card Copy · Step 1 / 2</p>
              <p className="mt-1 text-lg font-bold text-zinc-100">Place the front of your ID on the glass</p>
            </div>
            <KioskButton
              layout="tile"
              variant="primary"
              className="col-span-3 min-h-0 min-w-0 text-xl font-black uppercase tracking-wide"
              disabled={hardwareBusy}
              onClick={() => void scanFront()}
            >
              {busy === "front" ? "Scanning Front…" : "Scan Front"}
            </KioskButton>
          </div>
        </div>
      )}

      {step === "FLIP" && (
        <div className="flex min-h-0 flex-1 flex-col items-center justify-center">
          <div className="grid min-h-0 grid-cols-3 grid-rows-2 gap-3 md:gap-4" style={GRID_STYLE}>
            <KioskButton
              layout="tile"
              variant="industrialMuted"
              className="min-h-0 min-w-0"
              disabled={hardwareBusy}
              onClick={() => {
                void discardSession();
                setStep("START");
              }}
            >
              Cancel
            </KioskButton>
            <div className="col-span-2 flex flex-col justify-center rounded-2xl border border-kiosk-industrial-border bg-kiosk-industrial-navy p-4">
              <p className="text-sm font-bold uppercase tracking-wider text-zinc-400">ID Card Copy · Step 2 / 2</p>
              <p className="mt-1 text-lg font-bold text-zinc-100">Flip the ID over on the glass</p>
            </div>
            <KioskButton
              layout="tile"
              variant="primary"
              className="col-span-3 min-h-0 min-w-0 text-xl font-black uppercase tracking-wide"
              disabled={hardwareBusy}
              onClick={() => void scanBackAndCompose()}
            >
              {busy === "back" ? "Scanning Back…" : "Scan Back & Preview"}
            </KioskButton>
          </div>
        </div>
      )}

      {step === "PREVIEW" && (
        <div className="mx-auto flex min-h-0 w-full max-w-4xl flex-1 flex-col gap-3">
          <div className="flex shrink-0 items-center justify-between">
            <h2 className="text-lg font-black uppercase tracking-wide">ID Card A4 Preview</h2>
            <KioskButton
              variant="industrialMuted"
              className="min-h-[3rem] px-4"
              disabled={hardwareBusy}
              onClick={() => {
                void discardSession();
                setStep("START");
              }}
            >
              Start Over
            </KioskButton>
          </div>
          <div className="flex min-h-0 flex-1 items-center justify-center overflow-hidden rounded-2xl border border-kiosk-industrial-border bg-kiosk-industrial-navy p-3">
            {previewSrc ? (
              <img src={previewSrc} alt="Composed ID card preview" className="max-h-full max-w-full rounded object-contain" />
            ) : (
              <p className="text-zinc-400">Preview unavailable</p>
            )}
          </div>
          <div className="grid shrink-0 grid-cols-2 gap-3">
            <KioskButton
              variant="industrialMuted"
              className="min-h-[4rem] text-lg font-bold"
              disabled={hardwareBusy}
              onClick={() => {
                void discardSession();
                nav("/copy");
              }}
            >
              ← Done / Exit
            </KioskButton>
            <KioskButton
              variant="primary"
              className="min-h-[4rem] text-lg font-black uppercase"
              disabled={hardwareBusy}
              onClick={() => void doPrint()}
            >
              {busy === "print" ? "Printing…" : "Print A4 Copy"}
            </KioskButton>
          </div>
        </div>
      )}

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
