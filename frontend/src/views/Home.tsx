import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { apiUrl } from "../api";
import {
  IconCopy,
  IconDroplets,
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
  return d.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit", hour12: false });
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
      const res = await fetch(apiUrl("/api/hardware?include_devices=false"));
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

      {/* Top dashboard bar — HP 9010 style with Clock & Admin button */}
      <header className="flex shrink-0 items-center justify-between border-b border-kiosk-industrial-border bg-kiosk-industrial-navy px-4 py-3 md:px-6 md:py-3.5">
        <div className="min-w-0">
          <p className="text-[10px] font-semibold uppercase tracking-[0.2em] text-zinc-500">
            HP OfficeJet Pro 9010
          </p>
          <p className="truncate text-lg font-bold tracking-tight text-zinc-100 md:text-xl">
            Kopi Smart Station
          </p>
        </div>

        <div className="flex flex-col items-center gap-0.5 text-center">
          <time className="font-mono text-xl font-semibold tabular-nums text-zinc-100 md:text-2xl" dateTime={now.toISOString()}>
            {formatClock(now)}
          </time>
          <p className="text-xs text-zinc-500">{formatDate(now)}</p>
        </div>

        <div className="flex items-center gap-3">
          <div className="hidden flex-col items-end gap-0.5 text-right sm:flex">
            <p className={`text-sm font-bold uppercase tracking-wide ${statusColor}`}>{statusLabel}</p>
            <p className="text-[10px] uppercase tracking-wider text-zinc-500">System</p>
          </div>
          <button
            type="button"
            onClick={() => nav("/admin")}
            aria-label="Admin — PIN required"
            className="flex h-11 items-center gap-2 rounded-xl border border-amber-500/40 bg-kiosk-industrial-slate px-3.5 text-xs font-black uppercase tracking-wider text-amber-300 ring-1 ring-amber-500/20 active:scale-95"
          >
            <IconLock className="h-4 w-4 text-amber-400" />
            <span>Admin</span>
          </button>
        </div>
      </header>

      {/* Main HP 9010 3-Card Home Menu: Copy, Scan, Print from USB */}
      <main className="mx-auto flex min-h-0 w-full max-w-5xl flex-1 flex-col justify-center gap-4 px-4 py-3 md:grid md:grid-cols-3 md:items-stretch md:gap-6 md:px-8 md:py-6">
        <KioskButton
          layout="tile"
          variant="industrial"
          icon={<IconCopy className="text-emerald-400" />}
          className="min-h-[8.5rem] md:min-h-[16rem]"
          onClick={() => nav("/copy")}
        >
          <span className="block text-2xl font-black uppercase tracking-wide md:text-3xl">
            Copy
          </span>
          <span className="mt-1.5 block text-xs font-medium normal-case tracking-normal text-zinc-400">
            Document, ID Card & Photo Copy
          </span>
        </KioskButton>

        <KioskButton
          layout="tile"
          variant="industrial"
          icon={<IconScanLine className="text-cyan-400" />}
          className="min-h-[8.5rem] md:min-h-[16rem]"
          onClick={() => nav("/scan")}
        >
          <span className="block text-2xl font-black uppercase tracking-wide md:text-3xl">
            Scan
          </span>
          <span className="mt-1.5 block text-xs font-medium normal-case tracking-normal text-zinc-400">
            Scan to Email, USB Drive & Archive
          </span>
        </KioskButton>

        <KioskButton
          layout="tile"
          variant="industrial"
          icon={<IconUsb className="text-amber-400" />}
          className="min-h-[8.5rem] md:min-h-[16rem]"
          onClick={() => nav("/usb-print")}
        >
          <span className="block text-2xl font-black uppercase tracking-wide md:text-3xl">
            USB Print
          </span>
          <span className="mt-1.5 block text-xs font-medium normal-case tracking-normal text-zinc-400">
            Browse & Print Files from USB Flash Drive
          </span>
        </KioskButton>
      </main>

      {/* Bottom status bar — pinned */}
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
