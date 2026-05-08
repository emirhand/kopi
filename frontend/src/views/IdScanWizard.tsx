import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { apiUrl, parseErrorDetail } from "../api";
import { KioskButton } from "../components/KioskButton";
import { StatusModal } from "../components/StatusModal";

type WizardState = "START" | "FLIPPING" | "PREVIEW";

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
    <div className="flex h-full min-h-0 flex-col bg-kiosk-industrial-bezel p-4 text-zinc-100">
      <div className="flex shrink-0 items-center gap-3">
        <KioskButton
          variant="ghost"
          className="min-h-[3rem] px-4 text-base"
          disabled={hardwareBusy}
          onClick={() => {
            void discardSession();
            nav("/");
          }}
        >
          ← Home
        </KioskButton>
        <h1 className="text-xl font-black uppercase tracking-wide md:text-2xl">ID Scan</h1>
      </div>

      {ocrHint && (
        <p className="mt-2 shrink-0 text-center text-xs text-zinc-500">
          OCR may be applied to the PDF per Admin settings (requires ocrmypdf on the server).
        </p>
      )}

      <div className="mt-4 flex min-h-0 flex-1 flex-col gap-4 overflow-hidden">
        {step === "START" && (
          <div className="flex min-h-0 flex-1 flex-col justify-center gap-4">
            <div className="rounded-2xl border border-kiosk-industrial-border bg-kiosk-industrial-slate/50 p-4 text-center text-zinc-300">
              <p className="text-lg font-semibold text-zinc-100">Place card on glass</p>
              <p className="mt-2 text-sm leading-snug">
                Position the <strong className="text-zinc-100">front</strong> of your ID card face-down on the scanner,
                aligned for a standard ID-1 scan area.
              </p>
            </div>
            <KioskButton variant="primary" className="min-h-[4rem] w-full text-xl" disabled={hardwareBusy} onClick={scanFront}>
              {busy === "front" ? "Scanning…" : "Scan front"}
            </KioskButton>
          </div>
        )}

        {step === "FLIPPING" && (
          <div className="flex min-h-0 flex-1 flex-col justify-center gap-4">
            <div className="rounded-2xl border border-emerald-500/30 bg-emerald-950/20 p-4 text-center">
              <p className="text-lg font-bold uppercase tracking-wide text-emerald-400">Front captured</p>
              <p className="mt-3 text-sm text-zinc-300">
                Flip the card over and place the <strong className="text-zinc-100">back</strong> on the glass the same way.
              </p>
            </div>
            <KioskButton variant="primary" className="min-h-[4rem] w-full text-xl" disabled={hardwareBusy} onClick={scanBack}>
              {busy === "back" || busy === "compose" ? "Scanning…" : "Scan back"}
            </KioskButton>
          </div>
        )}

        {step === "PREVIEW" && (
          <div className="flex min-h-0 flex-1 flex-col gap-3 overflow-hidden">
            <div className="min-h-0 flex-1 overflow-auto rounded-2xl border border-kiosk-industrial-border bg-black/30 p-2">
              {previewSrc ? (
                <img src={previewSrc} alt="ID scan preview" className="mx-auto max-h-[50dvh] w-auto max-w-full object-contain" />
              ) : (
                <p className="p-4 text-center text-sm text-zinc-500">Preview unavailable; you can still print or email the PDF.</p>
              )}
            </div>
            <div className="flex shrink-0 flex-col gap-2 sm:flex-row">
              <KioskButton variant="primary" className="min-h-[3.5rem] flex-1 text-lg" disabled={hardwareBusy} onClick={doPrint}>
                {busy === "print" ? "Printing…" : "Print"}
              </KioskButton>
              <div className="flex flex-1 flex-col gap-2 sm:flex-row">
                <input
                  type="email"
                  inputMode="email"
                  placeholder="Email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="min-h-[3.5rem] flex-1 rounded-2xl border-2 border-kiosk-industrial-border bg-kiosk-industrial-navy px-4 text-zinc-100 placeholder:text-zinc-500"
                />
                <KioskButton
                  variant="secondary"
                  className="min-h-[3.5rem] flex-1 text-lg"
                  disabled={hardwareBusy}
                  onClick={doEmail}
                >
                  {busy === "email" ? "Sending…" : "Email"}
                </KioskButton>
              </div>
            </div>
            <KioskButton
              variant="ghost"
              className="min-h-12 w-full text-base"
              disabled={hardwareBusy}
              onClick={() => {
                void discardSession();
              }}
            >
              New ID scan
            </KioskButton>
          </div>
        )}
      </div>

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
