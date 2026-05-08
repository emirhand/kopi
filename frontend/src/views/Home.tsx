import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { apiUrl } from "../api";
import {
  IconCopy,
  IconDroplets,
  IconIdCard,
  IconInfo,
  IconLock,
  IconScanLine,
  IconUsb,
  IconWifi,
} from "../components/IndustrialIcons";
import { KioskButton } from "../components/KioskButton";
import { UsbStorageModal } from "../components/UsbStorageModal";
import type { HardwareInfo } from "../types/hardware";
import { KOPI_USB_MOUNT_STORAGE_KEY } from "../usbStorage";

export type { UsbVolumeInfo } from "../types/hardware";

function formatClock(d: Date) {
  return d.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false });
}

function formatDate(d: Date) {
  return d.toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric", year: "numeric" });
}

function normalizeHardware(data: unknown): HardwareInfo {
  const d = data as Record<string, unknown>;
  const rawUsb = d?.usb_volumes;
  let usb_volumes: HardwareInfo["usb_volumes"] = [];
  if (Array.isArray(rawUsb)) {
    usb_volumes = rawUsb.map((x) => {
      if (typeof x === "string") {
        return {
          device: "",
          mountpoint: x,
          label: x.split("/").filter(Boolean).pop() || x,
          model: "",
          mounted: true,
        };
      }
      const o = x as Record<string, unknown>;
      return {
        device: String(o.device ?? ""),
        mountpoint: o.mountpoint != null ? String(o.mountpoint) : null,
        label: String(o.label ?? ""),
        model: String(o.model ?? ""),
        mounted: Boolean(o.mounted),
      };
    });
  }
  return {
    scanners: Array.isArray(d?.scanners) ? (d.scanners as string[]) : [],
    printers: Array.isArray(d?.printers) ? (d.printers as string[]) : [],
    usb_volumes,
  };
}

function readSelectedUsb(): string | null {
  try {
    const v = sessionStorage.getItem(KOPI_USB_MOUNT_STORAGE_KEY);
    return v && v.trim() ? v.trim() : null;
  } catch {
    return null;
  }
}

export function Home() {
  const nav = useNavigate();
  const [now, setNow] = useState(() => new Date());
  const [hardware, setHardware] = useState<HardwareInfo>({ scanners: [], printers: [], usb_volumes: [] });
  const [systemStatus, setSystemStatus] = useState<"ok" | "offline" | "checking">("checking");
  const [usbModalOpen, setUsbModalOpen] = useState(false);
  const [selectedUsbMount, setSelectedUsbMount] = useState<string | null>(() => readSelectedUsb());
  const [hardwareHydrated, setHardwareHydrated] = useState(false);

  const refreshHardware = useCallback(async () => {
    try {
      const res = await fetch(apiUrl("/api/hardware"));
      if (!res.ok) return;
      const data = await res.json();
      setHardware(normalizeHardware(data));
      setHardwareHydrated(true);
    } catch {
      /* ignore */
    }
  }, []);

  useEffect(() => {
    const t = window.setInterval(() => setNow(new Date()), 1000);
    return () => window.clearInterval(t);
  }, []);

  useEffect(() => {
    void refreshHardware();
  }, [refreshHardware]);

  useEffect(() => {
    const id = window.setInterval(refreshHardware, 8000);
    return () => window.clearInterval(id);
  }, [refreshHardware]);

  useEffect(() => {
    if (!hardwareHydrated) return;
    const sel = readSelectedUsb();
    if (!sel) return;
    const mounted = hardware.usb_volumes.filter((v) => v.mounted && v.mountpoint);
    if (mounted.length === 0) {
      try {
        sessionStorage.removeItem(KOPI_USB_MOUNT_STORAGE_KEY);
      } catch {
        /* ignore */
      }
      setSelectedUsbMount(null);
      return;
    }
    if (!mounted.some((v) => v.mountpoint === sel)) {
      try {
        sessionStorage.removeItem(KOPI_USB_MOUNT_STORAGE_KEY);
      } catch {
        /* ignore */
      }
      setSelectedUsbMount(null);
    }
  }, [hardware.usb_volumes, hardwareHydrated]);

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
    const hid = window.setInterval(async () => {
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
      window.clearInterval(hid);
    };
  }, []);

  const mountedUsb = hardware.usb_volumes.filter((v) => v.mounted && v.mountpoint);
  const usbFooterLabel = (() => {
    if (selectedUsbMount) {
      const match = hardware.usb_volumes.find((v) => v.mountpoint === selectedUsbMount);
      const name = match?.label || selectedUsbMount.split("/").filter(Boolean).pop() || selectedUsbMount;
      return name;
    }
    if (mountedUsb.length === 0) return "None";
    if (mountedUsb.length === 1 && mountedUsb[0].mountpoint) {
      return `${mountedUsb[0].label || "USB"} — tap to choose`;
    }
    return `${mountedUsb.length} drive(s) — tap to choose`;
  })();

  function selectUsbMount(mountPath: string) {
    try {
      sessionStorage.setItem(KOPI_USB_MOUNT_STORAGE_KEY, mountPath);
    } catch {
      /* ignore */
    }
    setSelectedUsbMount(mountPath);
  }

  const statusLabel =
    systemStatus === "ok" ? "Ready" : systemStatus === "offline" ? "Service offline" : "Checking…";
  const statusColor =
    systemStatus === "ok" ? "text-emerald-400" : systemStatus === "offline" ? "text-red-400" : "text-amber-400";

  return (
    <div className="flex h-[100dvh] w-[100dvw] flex-col overflow-hidden bg-kiosk-industrial-bezel font-kiosk text-zinc-100">
      <UsbStorageModal
        open={usbModalOpen}
        onClose={() => setUsbModalOpen(false)}
        volumes={hardware.usb_volumes}
        selectedMountPath={selectedUsbMount}
        onSelectMount={(mp) => {
          selectUsbMount(mp);
        }}
        onRefresh={refreshHardware}
      />

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

          <KioskButton
            layout="tile"
            variant="industrial"
            icon={<IconIdCard className="text-violet-400" />}
            className="min-h-0 min-w-0"
            onClick={() => nav("/id-scan")}
          >
            ID Scan
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
        <button
          type="button"
          onClick={() => setUsbModalOpen(true)}
          className="flex min-w-0 flex-1 items-center gap-2 rounded-lg border border-kiosk-industrial-border/80 bg-kiosk-industrial-slate/50 px-3 py-2 text-left transition-colors active:bg-kiosk-industrial-slate active:scale-[0.98]"
        >
          <IconUsb className="h-5 w-5 shrink-0 text-zinc-500" />
          <div className="min-w-0">
            <p className="text-[10px] font-semibold uppercase tracking-wider text-zinc-500">USB</p>
            <p className="truncate text-sm font-bold text-zinc-300">{usbFooterLabel}</p>
          </div>
        </button>
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
