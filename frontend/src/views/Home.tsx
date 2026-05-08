import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { apiUrl } from "../api";
import {
  IconArchive,
  IconCopy,
  IconDroplets,
  IconInfo,
  IconLock,
  IconScanLine,
  IconUsb,
  IconWifi,
} from "../components/IndustrialIcons";
import { KioskButton } from "../components/KioskButton";

type HardwareInfo = {
  scanners: string[];
  printers: string[];
  usb_volumes: string[];
};

function formatClock(d: Date) {
  return d.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false });
}

function formatDate(d: Date) {
  return d.toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric", year: "numeric" });
}

export function Home() {
  const nav = useNavigate();
  const [now, setNow] = useState(() => new Date());
  const [hardware, setHardware] = useState<HardwareInfo>({ scanners: [], printers: [], usb_volumes: [] });
  const [systemStatus, setSystemStatus] = useState<"ok" | "offline" | "checking">("checking");

  useEffect(() => {
    const t = window.setInterval(() => setNow(new Date()), 1000);
    return () => window.clearInterval(t);
  }, []);

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
        /* ignore */
      }
    })();
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    let active = true;
    (async () => {
      try {
        const res = await fetch(apiUrl("/api/health"));
        if (!active) return;
        setSystemStatus(res.ok ? "ok" : "offline");
      } catch {
        if (active) setSystemStatus("offline");
      }
    })();
    const id = window.setInterval(async () => {
      try {
        const res = await fetch(apiUrl("/api/health"));
        if (!active) return;
        setSystemStatus(res.ok ? "ok" : "offline");
      } catch {
        if (active) setSystemStatus("offline");
      }
    }, 15000);
    return () => {
      active = false;
      window.clearInterval(id);
    };
  }, []);

  const statusLabel =
    systemStatus === "ok" ? "Ready" : systemStatus === "offline" ? "Service offline" : "Checking…";
  const statusColor =
    systemStatus === "ok" ? "text-emerald-400" : systemStatus === "offline" ? "text-red-400" : "text-amber-400";

  return (
    <div className="flex h-[100dvh] w-[100dvw] flex-col overflow-hidden bg-kiosk-industrial-bezel font-kiosk text-zinc-100">
      {/* Top bar — pinned */}
      <header className="flex shrink-0 items-center justify-between border-b border-kiosk-industrial-border bg-kiosk-industrial-navy px-4 py-3 md:px-6 md:py-3.5">
        <div className="min-w-0">
          <p className="text-[10px] font-semibold uppercase tracking-[0.2em] text-zinc-500">Kopi</p>
          <p className="truncate text-lg font-bold tracking-tight text-zinc-100 md:text-xl">Smart Copier</p>
        </div>
        <div className="flex flex-col items-end gap-0.5 text-right">
          <time className="font-mono text-xl font-semibold tabular-nums text-zinc-100 md:text-2xl" dateTime={now.toISOString()}>
            {formatClock(now)}
          </time>
          <p className="text-xs text-zinc-500">{formatDate(now)}</p>
        </div>
        <div className="flex min-w-[7rem] flex-col items-end gap-0.5 text-right md:min-w-[9rem]">
          <p className={`text-sm font-bold uppercase tracking-wide ${statusColor}`}>{statusLabel}</p>
          <p className="text-[10px] uppercase tracking-wider text-zinc-500">System</p>
        </div>
      </header>

      {/* Main 3×2 grid — centered, locked viewport */}
      <main className="flex min-h-0 flex-1 items-center justify-center px-4 py-3 md:px-8 md:py-5">
        <div
          className="grid min-h-0 w-full grid-cols-3 grid-rows-2 gap-3 md:gap-4"
          style={{
            width: "min(92vw, calc((100dvh - 9.5rem) * 3 / 2))",
            height: "min(calc(100dvh - 9.5rem), calc(min(92vw, (100dvh - 9.5rem) * 3 / 2) * 2 / 3))",
          }}
        >
          <KioskButton
            layout="tile"
            variant="industrial"
            icon={<IconCopy className="text-emerald-400" />}
            className="min-h-0 min-w-0"
            onClick={() => nav("/copy")}
          >
            Copy
          </KioskButton>

          <KioskButton
            layout="tile"
            variant="industrial"
            icon={<IconScanLine className="text-cyan-400" />}
            className="min-h-0 min-w-0"
            onClick={() => nav("/scan")}
          >
            Scan
          </KioskButton>

          <KioskButton layout="tile" variant="industrialMuted" icon={<IconUsb className="text-zinc-500" />} disabled badge="Soon">
            USB Print
          </KioskButton>

          <KioskButton layout="tile" variant="industrialMuted" icon={<IconArchive className="text-zinc-500" />} disabled badge="Soon">
            File Archive
          </KioskButton>

          <KioskButton layout="tile" variant="industrialMuted" icon={<IconInfo className="text-zinc-500" />} disabled badge="Soon">
            System Info
          </KioskButton>

          <KioskButton
            layout="tile"
            variant="industrial"
            icon={<IconLock className="text-amber-400" />}
            className="min-h-0 min-w-0 ring-1 ring-amber-500/30"
            badge="PIN"
            onClick={() => nav("/admin")}
            aria-label="Admin — PIN required"
          >
            Admin
          </KioskButton>
        </div>
      </main>

      {/* Bottom bar — pinned */}
      <footer className="flex shrink-0 items-stretch justify-between gap-2 border-t border-kiosk-industrial-border bg-kiosk-industrial-navy px-3 py-2.5 md:px-6 md:py-3">
        <div className="flex min-w-0 flex-1 items-center gap-2 rounded-lg border border-kiosk-industrial-border/80 bg-kiosk-industrial-slate/50 px-3 py-2">
          <IconDroplets className="h-5 w-5 shrink-0 text-zinc-500" />
          <div className="min-w-0">
            <p className="text-[10px] font-semibold uppercase tracking-wider text-zinc-500">Ink / Supplies</p>
            <p className="truncate text-sm font-bold text-zinc-300">OK</p>
          </div>
        </div>
        <div className="flex min-w-0 flex-1 items-center gap-2 rounded-lg border border-kiosk-industrial-border/80 bg-kiosk-industrial-slate/50 px-3 py-2">
          <IconUsb className="h-5 w-5 shrink-0 text-zinc-500" />
          <div className="min-w-0">
            <p className="text-[10px] font-semibold uppercase tracking-wider text-zinc-500">USB</p>
            <p className="truncate text-sm font-bold text-zinc-300">
              {hardware.usb_volumes.length ? `${hardware.usb_volumes.length} volume(s)` : "None"}
            </p>
          </div>
        </div>
        <div className="flex min-w-0 flex-1 items-center gap-2 rounded-lg border border-kiosk-industrial-border/80 bg-kiosk-industrial-slate/50 px-3 py-2">
          <IconWifi className="h-5 w-5 shrink-0 text-zinc-500" />
          <div className="min-w-0">
            <p className="text-[10px] font-semibold uppercase tracking-wider text-zinc-500">Network</p>
            <p className="truncate text-sm font-bold text-zinc-300">LAN</p>
          </div>
        </div>
      </footer>
    </div>
  );
}
