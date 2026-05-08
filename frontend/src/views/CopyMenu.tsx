import type { CSSProperties } from "react";
import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { apiUrl, parseErrorDetail } from "../api";
import { KioskButton } from "../components/KioskButton";
import { ProgressBar } from "../components/ProgressBar";

type Stage = "idle" | "scanning" | "printing" | "done" | "error";

/** Matches Home main grid aspect — Back top-left, Start bottom-right (Admin corner). */
const GRID_STYLE: CSSProperties = {
  width: "min(92vw, calc((100dvh - 10rem) * 3 / 2))",
  height:
    "min(calc(100dvh - 10rem), calc(min(92vw, (100dvh - 10rem) * 3 / 2) * 2 / 3))",
};

export function CopyMenu() {
  const nav = useNavigate();
  const [duplex, setDuplex] = useState(false);
  const [color, setColor] = useState(true);
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
        body: JSON.stringify({
          duplex,
          color,
          resolution_dpi: 300,
        }),
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
    <div className="flex h-[100dvh] w-[100dvw] flex-col overflow-hidden bg-kiosk-industrial-bezel text-zinc-100">
      <header className="shrink-0 px-4 pt-3 text-center">
        <p className="text-[10px] font-semibold uppercase tracking-wider text-zinc-500">Copier</p>
        <h1 className="text-xl font-black uppercase tracking-wide text-zinc-100 md:text-2xl">Copy</h1>
      </header>

      <main className="flex min-h-0 flex-1 items-center justify-center px-3 py-2 md:px-6">
        {stage === "scanning" && (
          <div className="w-full max-w-xl px-2">
            <ProgressBar label="Scanning…" variant="scan" />
          </div>
        )}
        {stage === "printing" && (
          <div className="w-full max-w-xl px-2">
            <ProgressBar label="Printing…" variant="print" />
          </div>
        )}

        {stage === "done" && (
          <div className="flex max-w-xl flex-col items-center rounded-3xl border-2 border-emerald-500/40 bg-kiosk-industrial-slate/80 p-8 text-center shadow-xl">
            <p className="text-3xl font-black text-zinc-100 md:text-4xl">Done</p>
            <p className="mt-3 text-lg text-zinc-400">Your print job was submitted.</p>
          </div>
        )}

        {stage === "error" && errorDetail && (
          <div className="max-h-[min(70dvh,28rem)] w-full max-w-xl overflow-auto rounded-3xl border-2 border-red-500/50 bg-kiosk-industrial-slate/90 p-6 shadow-xl">
            <p className="text-2xl font-black text-zinc-100">Check hardware</p>
            <p className="mt-3 whitespace-pre-wrap text-lg leading-snug text-zinc-400">{errorDetail}</p>
            <KioskButton
              variant="primary"
              className="mt-6 min-h-[3.5rem] w-full max-w-sm mx-auto text-xl"
              onClick={resetFromError}
            >
              Try Again
            </KioskButton>
          </div>
        )}

        {stage === "idle" && (
          <div
            className="grid min-h-0 grid-cols-3 grid-rows-2 gap-3 md:gap-4"
            style={GRID_STYLE}
          >
            <KioskButton
              layout="tile"
              variant="industrialMuted"
              className="min-h-0 min-w-0"
              disabled={hardwareBusy}
              onClick={() => nav("/")}
            >
              ← Back
            </KioskButton>

            <KioskButton
              layout="tile"
              variant="industrial"
              tileActive={!duplex}
              className="min-h-0 min-w-0"
              disabled={hardwareBusy}
              onClick={() => setDuplex(false)}
            >
              Single-Sided
            </KioskButton>

            <KioskButton
              layout="tile"
              variant="industrial"
              tileActive={duplex}
              className="min-h-0 min-w-0"
              disabled={hardwareBusy}
              onClick={() => setDuplex(true)}
            >
              Duplex
            </KioskButton>

            <KioskButton
              layout="tile"
              variant="industrial"
              tileActive={color}
              className="min-h-0 min-w-0"
              disabled={hardwareBusy}
              onClick={() => setColor(true)}
            >
              Color
            </KioskButton>

            <KioskButton
              layout="tile"
              variant="industrial"
              tileActive={!color}
              className="min-h-0 min-w-0"
              disabled={hardwareBusy}
              onClick={() => setColor(false)}
            >
              B&amp;W
            </KioskButton>

            <KioskButton
              layout="tile"
              variant="industrial"
              className="min-h-0 min-w-0 ring-1 ring-amber-500/30"
              disabled={hardwareBusy}
              onClick={startCopy}
            >
              Start
            </KioskButton>
          </div>
        )}
      </main>
    </div>
  );
}
