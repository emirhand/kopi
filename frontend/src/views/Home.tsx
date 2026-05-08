import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { apiUrl } from "../api";
import { KioskButton } from "../components/KioskButton";

type HardwareInfo = {
  scanners: string[];
  printers: string[];
  usb_volumes: string[];
};

export function Home() {
  const nav = useNavigate();
  const [hardware, setHardware] = useState<HardwareInfo>({ scanners: [], printers: [], usb_volumes: [] });

  useEffect(() => {
    let active = true;
    (async () => {
      try {
        const res = await fetch(apiUrl("/api/hardware"));
        if (!res.ok) return;
        const data = await res.json();
        if (!active) return;
        setHardware({
          scanners: Array.isArray(data?.scanners) ? data.scanners : [],
          printers: Array.isArray(data?.printers) ? data.printers : [],
          usb_volumes: Array.isArray(data?.usb_volumes) ? data.usb_volumes : [],
        });
      } catch {
        // Keep panel silent on network/hardware lookup failures.
      }
    })();
    return () => {
      active = false;
    };
  }, []);

  return (
    <div className="h-[100dvh] w-[100dvw] flex flex-col bg-kiosk-bg overflow-hidden">
      <header className="shrink-0 px-4 pt-4 pb-2 flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h1 className="text-2xl md:text-4xl font-black tracking-tight text-kiosk-text leading-tight">
            Smart Copier
          </h1>
          <p className="mt-1 text-sm md:text-base text-kiosk-muted">Tap a task to begin</p>
        </div>
        <button
          type="button"
          onClick={() => nav("/admin")}
          className="shrink-0 rounded-2xl border-2 border-white/15 bg-kiosk-panel px-4 py-3 text-sm md:text-base font-semibold text-kiosk-muted active:scale-[0.98] min-h-[3rem] min-w-[6rem]"
        >
          Admin
        </button>
      </header>

      <main className="flex-1 min-h-0 p-3 md:p-4 flex gap-3 md:gap-4">
        <aside className="w-[34%] min-w-[18rem] max-w-[32rem] rounded-2xl border-2 border-white/15 bg-kiosk-panel p-3 overflow-auto">
          <h3 className="text-base md:text-lg font-bold text-kiosk-text">Detected Hardware</h3>

          <section className="mt-3">
            <p className="text-xs uppercase tracking-wide text-kiosk-muted">Printers</p>
            <ul className="mt-1 space-y-1 text-sm text-kiosk-text break-all">
              {(hardware.printers.length ? hardware.printers : ["No printers detected"]).map((x) => (
                <li key={`p-${x}`} className="rounded-md bg-black/20 px-2 py-1">
                  {x}
                </li>
              ))}
            </ul>
          </section>

          <section className="mt-3">
            <p className="text-xs uppercase tracking-wide text-kiosk-muted">Scanners</p>
            <ul className="mt-1 space-y-1 text-sm text-kiosk-text break-all">
              {(hardware.scanners.length ? hardware.scanners : ["No scanners detected"]).map((x) => (
                <li key={`s-${x}`} className="rounded-md bg-black/20 px-2 py-1">
                  {x}
                </li>
              ))}
            </ul>
          </section>

          <section className="mt-3">
            <p className="text-xs uppercase tracking-wide text-kiosk-muted">USB Volumes</p>
            <ul className="mt-1 space-y-1 text-sm text-kiosk-text break-all">
              {(hardware.usb_volumes.length ? hardware.usb_volumes : ["No volumes detected"]).map((x) => (
                <li key={`u-${x}`} className="rounded-md bg-black/20 px-2 py-1">
                  {x}
                </li>
              ))}
            </ul>
          </section>
        </aside>

        <section className="flex-1 min-h-0 flex flex-col gap-3 md:gap-4">
          <KioskButton
            variant="primary"
            className="flex-1 w-full min-h-0 text-4xl sm:text-5xl md:text-6xl font-black uppercase ring-2 ring-white/10 active:scale-[0.99]"
            onClick={() => nav("/copy")}
          >
            Copy
          </KioskButton>
          <KioskButton
            variant="secondary"
            className="flex-1 w-full min-h-0 text-4xl sm:text-5xl md:text-6xl font-black uppercase border-kiosk-accent2/50 ring-2 ring-kiosk-accent2/20 active:scale-[0.99]"
            onClick={() => nav("/scan")}
          >
            Scan
          </KioskButton>
        </section>
      </main>
    </div>
  );
}
