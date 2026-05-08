import type { CSSProperties } from "react";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { apiUrl, parseErrorDetail } from "../api";
import { KioskButton } from "../components/KioskButton";
import { StatusModal } from "../components/StatusModal";

type WizardState = "START" | "FLIPPING" | "PREVIEW";

const GRID_STYLE: CSSProperties = {
  width: "min(92vw, calc((100dvh - 10rem) * 3 / 2))",
  height:
    "min(calc(100dvh - 10rem), calc(min(92vw, (100dvh - 10rem) * 3 / 2) * 2 / 3))",
};

export function IdScanWizard() {
  const nav = useNavigate();
  const [step, setStep] = useState<WizardState>("START");
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [previewSrc, setPreviewSrc] = useState<string | null>(null);
  const [ocrHint, setOcrHint] = useState(false);
  const [email, setEmail] = useState("");
  const [modal, setModal] = useState<{ title: string; message: string; variant: "info" | "error" } | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch(apiUrl("/api/settings/public"));
        if (!res.ok || cancelled) return;
        const data = await res.json();
        if (!cancelled) setOcrHint(Boolean(data?.id_scan_ocr));
      } catch {
        /* ignore */
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  async function discardSession() {
    if (!sessionId) return;
    try {
      await fetch(apiUrl("/api/id-scan/discard"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: sessionId }),
      });
    } catch {
      /* ignore */
    }
    setSessionId(null);
    setPreviewSrc(null);
    setStep("START");
  }

  async function scanFront() {
    setBusy("front");
    setModal(null);
    try {
      const res = await fetch(apiUrl("/api/id-scan/front"), { method: "POST" });
      if (!res.ok) {
        setModal({ title: "ID Scan", message: await parseErrorDetail(res), variant: "error" });
        return;
      }
      const data = await res.json();
      const sid = data.session_id as string;
      setSessionId(sid);
      setStep("FLIPPING");
    } catch (e) {
      setModal({
        title: "ID Scan",
        message: e instanceof Error ? e.message : "Network error",
        variant: "error",
      });
    } finally {
      setBusy(null);
    }
  }

  async function scanBack() {
    if (!sessionId) return;
    setBusy("back");
    try {
      const res = await fetch(apiUrl("/api/id-scan/back"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: sessionId }),
      });
      if (!res.ok) {
        setModal({ title: "ID Scan", message: await parseErrorDetail(res), variant: "error" });
        return;
      }
      setBusy("compose");
      const cres = await fetch(apiUrl("/api/id-scan/compose"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: sessionId }),
      });
      if (!cres.ok) {
        setModal({ title: "ID Scan", message: await parseErrorDetail(cres), variant: "error" });
        return;
      }
      const cdata = await cres.json();
      const b64 = cdata.preview_base64 as string | undefined;
      if (b64) setPreviewSrc(`data:image/png;base64,${b64}`);
      else setPreviewSrc(null);
      if (typeof cdata.ocr_applied === "boolean" && cdata.ocr_applied) {
        setOcrHint(true);
      }
      setStep("PREVIEW");
    } catch (e) {
      setModal({
        title: "ID Scan",
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
      const res = await fetch(apiUrl("/api/id-scan/print"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: sessionId }),
      });
      if (!res.ok) {
        setModal({ title: "Print", message: await parseErrorDetail(res), variant: "error" });
        return;
      }
      const data = await res.json();
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

  async function doEmail() {
    if (!sessionId || !email.trim()) {
      setModal({ title: "Email", message: "Enter an email address.", variant: "error" });
      return;
    }
    setBusy("email");
    try {
      const res = await fetch(apiUrl("/api/id-scan/email"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: sessionId, recipient: email.trim() }),
      });
      if (!res.ok) {
        setModal({ title: "Email", message: await parseErrorDetail(res), variant: "error" });
        return;
      }
      setModal({ title: "Email", message: "ID scan emailed.", variant: "info" });
    } catch (e) {
      setModal({
        title: "Email",
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
      {ocrHint && (
        <p className="mb-2 shrink-0 text-center text-xs text-zinc-500">
          OCR may be applied to the PDF per Admin settings (requires ocrmypdf on the server).
        </p>
      )}

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
                nav("/");
              }}
            >
              ← Home
            </KioskButton>
            <div className="col-span-2 flex min-h-0 items-center justify-center rounded-3xl border border-kiosk-industrial-border bg-kiosk-industrial-slate/50 p-4 text-center">
              <div>
                <p className="text-base font-semibold text-zinc-100 md:text-lg">Place card on glass</p>
                <p className="mt-2 text-xs leading-snug text-zinc-400 md:text-sm">
                  Position the <strong className="text-zinc-200">front</strong> of your ID face-down on the scanner.
                </p>
              </div>
            </div>
            <div className="min-h-0 min-w-0" aria-hidden />
            <KioskButton
              layout="tile"
              variant="industrial"
              className="min-h-0 min-w-0 ring-1 ring-emerald-500/30"
              disabled={hardwareBusy}
              onClick={scanFront}
            >
              {busy === "front" ? "…" : "Front"}
            </KioskButton>
            <div className="min-h-0 min-w-0" aria-hidden />
          </div>
        </div>
      )}

      {step === "FLIPPING" && (
        <div className="flex min-h-0 flex-1 flex-col items-center justify-center">
          <div className="grid min-h-0 grid-cols-3 grid-rows-2 gap-3 md:gap-4" style={GRID_STYLE}>
            <KioskButton
              layout="tile"
              variant="industrialMuted"
              className="min-h-0 min-w-0"
              disabled={hardwareBusy}
              onClick={() => {
                void discardSession();
                nav("/");
              }}
            >
              ← Home
            </KioskButton>
            <div className="col-span-2 flex min-h-0 items-center justify-center rounded-3xl border border-emerald-500/30 bg-emerald-950/20 p-4 text-center">
              <div>
                <p className="text-base font-bold uppercase tracking-wide text-emerald-400 md:text-lg">Front captured</p>
                <p className="mt-2 text-xs leading-snug text-zinc-300 md:text-sm">
                  Flip the card and place the <strong className="text-zinc-100">back</strong> on the glass the same way.
                </p>
              </div>
            </div>
            <div className="min-h-0 min-w-0" aria-hidden />
            <KioskButton
              layout="tile"
              variant="industrial"
              className="min-h-0 min-w-0 ring-1 ring-emerald-500/30"
              disabled={hardwareBusy}
              onClick={scanBack}
            >
              {busy === "back" || busy === "compose" ? "…" : "Back"}
            </KioskButton>
            <div className="min-h-0 min-w-0" aria-hidden />
          </div>
        </div>
      )}

      {step === "PREVIEW" && (
        <div className="flex min-h-0 flex-1 flex-col gap-3 overflow-hidden">
          <div
            className="grid shrink-0 grid-cols-3 gap-3 md:gap-4"
            style={{
              width: GRID_STYLE.width,
              height: "min(5.5rem, 22vw)",
              marginLeft: "auto",
              marginRight: "auto",
            }}
          >
            <KioskButton
              layout="tile"
              variant="industrialMuted"
              className="min-h-0 min-w-0"
              disabled={hardwareBusy}
              onClick={() => {
                void discardSession();
                nav("/");
              }}
            >
              ← Home
            </KioskButton>
            <div className="col-span-2 flex items-center justify-center rounded-3xl border border-kiosk-industrial-border bg-kiosk-industrial-slate/40 px-3">
              <p className="text-center text-sm font-black uppercase tracking-wide text-zinc-300 md:text-base">Preview</p>
            </div>
          </div>

          <div className="min-h-0 flex-1 overflow-auto rounded-2xl border border-kiosk-industrial-border bg-black/30 p-2">
            {previewSrc ? (
              <img src={previewSrc} alt="ID scan preview" className="mx-auto max-h-[min(48dvh,420px)] w-auto max-w-full object-contain" />
            ) : (
              <p className="p-4 text-center text-sm text-zinc-500">
                Preview unavailable; you can still print or email the PDF.
              </p>
            )}
          </div>

          <div className="grid shrink-0 grid-cols-2 gap-3 md:grid-cols-4 md:gap-4">
            <KioskButton layout="tile" variant="industrial" className="min-h-[5rem] md:col-span-1" disabled={hardwareBusy} onClick={doPrint}>
              {busy === "print" ? "…" : "Print"}
            </KioskButton>
            <div className="flex min-h-[5rem] flex-col gap-2 md:col-span-2">
              <input
                type="email"
                inputMode="email"
                placeholder="Email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                disabled={hardwareBusy}
                className="min-h-11 w-full rounded-2xl border-2 border-kiosk-industrial-border bg-kiosk-industrial-navy px-3 text-zinc-100 placeholder:text-zinc-500"
              />
              <KioskButton variant="secondary" className="min-h-11 w-full text-base" disabled={hardwareBusy} onClick={doEmail}>
                {busy === "email" ? "…" : "Email"}
              </KioskButton>
            </div>
            <KioskButton
              layout="tile"
              variant="industrialMuted"
              className="min-h-[5rem]"
              disabled={hardwareBusy}
              onClick={() => {
                void discardSession();
              }}
            >
              New scan
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
