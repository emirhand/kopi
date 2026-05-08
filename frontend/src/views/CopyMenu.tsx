import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { apiUrl, parseErrorDetail } from "../api";
import { KioskButton } from "../components/KioskButton";
import { ProgressBar } from "../components/ProgressBar";

type Stage = "idle" | "scanning" | "printing" | "done" | "error";

export function CopyMenu() {
  const nav = useNavigate();
  const [duplex, setDuplex] = useState(false);
  const [stage, setStage] = useState<Stage>("idle");
  const [errorDetail, setErrorDetail] = useState<string | null>(null);
  const busyLock = useRef(false);

  const hardwareBusy = stage === "scanning" || stage === "printing";

  useEffect(() => {
    if (stage !== "done") return;
    const t = window.setTimeout(() => {
      setStage("idle");
      busyLock.current = false;
    }, 2000);
    return () => window.clearTimeout(t);
  }, [stage]);

  async function startCopy() {
    if (busyLock.current) return;
    busyLock.current = true;
    setErrorDetail(null);

    setStage("scanning");

    let scanId: string;
    try {
      const scanRes = await fetch(apiUrl("/api/scan"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ duplex }),
      });
      if (!scanRes.ok) {
        const msg = await parseErrorDetail(scanRes);
        setErrorDetail(msg);
        setStage("error");
        busyLock.current = false;
        return;
      }
      const data = await scanRes.json();
      scanId = data.scan_id as string;
    } catch (e) {
      setErrorDetail(e instanceof Error ? e.message : "Network error");
      setStage("error");
      busyLock.current = false;
      return;
    }

    setStage("printing");
    try {
      const printRes = await fetch(apiUrl("/api/print"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ scan_id: scanId, duplex }),
      });
      if (!printRes.ok) {
        const msg = await parseErrorDetail(printRes);
        setErrorDetail(msg);
        setStage("error");
        busyLock.current = false;
        return;
      }
      setStage("done");
      busyLock.current = false;
    } catch (e) {
      setErrorDetail(e instanceof Error ? e.message : "Network error");
      setStage("error");
      busyLock.current = false;
    }
  }

  function resetFromError() {
    setErrorDetail(null);
    setStage("idle");
    busyLock.current = false;
  }

  return (
    <div className="h-[100dvh] w-[100dvw] flex flex-col bg-kiosk-bg overflow-hidden p-3 md:p-4 gap-3">
      <div className="shrink-0 flex items-center gap-3">
        <KioskButton
          variant="ghost"
          className="min-h-[3.5rem] px-5 text-lg"
          disabled={hardwareBusy}
          onClick={() => nav("/")}
        >
          ← Back
        </KioskButton>
        <h2 className="text-2xl md:text-3xl font-black">Copy</h2>
      </div>

      <KioskButton
        variant={duplex ? "primary" : "secondary"}
        className="shrink-0 w-full text-xl md:text-2xl min-h-[4rem] ring-2 ring-white/10 active:scale-[0.99]"
        disabled={stage !== "idle"}
        onClick={() => setDuplex((v) => !v)}
      >
        Duplex: {duplex ? "On" : "Off"}
      </KioskButton>

      <div className="flex-1 min-h-0 flex flex-col gap-4">
        {stage === "scanning" && <ProgressBar label="Scanning…" variant="scan" />}
        {stage === "printing" && <ProgressBar label="Printing…" variant="print" />}

        {stage === "done" && (
          <div className="flex-1 flex items-center justify-center">
            <div className="w-full max-w-xl rounded-3xl border-4 border-kiosk-accent2 bg-kiosk-panel p-8 text-center shadow-xl shadow-black/50">
              <p className="text-3xl md:text-4xl font-black text-kiosk-text">Done</p>
              <p className="mt-3 text-lg text-kiosk-muted">Your print job was submitted.</p>
            </div>
          </div>
        )}

        {stage === "error" && errorDetail && (
          <div className="flex-1 flex items-center justify-center">
            <div className="w-full max-w-xl rounded-3xl border-4 border-kiosk-danger bg-kiosk-panel p-6 md:p-8 shadow-xl shadow-black/50">
              <p className="text-2xl md:text-3xl font-black text-kiosk-text">Check hardware</p>
              <p className="mt-3 text-lg text-kiosk-muted whitespace-pre-wrap leading-snug">
                {errorDetail}
              </p>
              <KioskButton
                variant="primary"
                className="mt-6 w-full text-2xl ring-2 ring-white/10 active:scale-[0.99]"
                onClick={resetFromError}
              >
                Try Again
              </KioskButton>
            </div>
          </div>
        )}

        {stage === "idle" && (
          <KioskButton
            variant="primary"
            className="flex-1 min-h-0 w-full text-3xl md:text-5xl font-black ring-2 ring-white/10 active:scale-[0.99]"
            onClick={startCopy}
          >
            Start Copy
          </KioskButton>
        )}
      </div>
    </div>
  );
}
