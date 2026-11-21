import { useState } from "react";
import { apiUrl, parseErrorDetail } from "../api";
import { KioskButton } from "./KioskButton";
import type { UsbVolumeInfo } from "../types/hardware";

type Props = {
  open: boolean;
  onClose: () => void;
  volumes: UsbVolumeInfo[];
  selectedMountPath: string | null;
  onSelectMount: (mountPath: string) => void;
  onRefresh: () => void;
};

export function UsbStorageModal({
  open,
  onClose,
  volumes,
  selectedMountPath,
  onSelectMount,
  onRefresh,
}: Props) {
  const [busyDevice, setBusyDevice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  if (!open) return null;

  async function mountDevice(device: string) {
    setError(null);
    setBusyDevice(device);
    try {
      const res = await fetch(apiUrl("/api/usb/mount"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ device }),
      });
      const data = res.ok ? await res.json().catch(() => ({})) : null;
      if (!res.ok) {
        setError(await parseErrorDetail(res));
        return;
      }
      const mp = typeof data?.mountpoint === "string" ? data.mountpoint : null;
      onRefresh();
      if (mp) onSelectMount(mp);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Network error");
    } finally {
      setBusyDevice(null);
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="usb-storage-title"
    >
      <div className="flex max-h-[85dvh] w-full max-w-lg flex-col rounded-3xl border-2 border-kiosk-industrial-border bg-kiosk-industrial-navy shadow-[0_8px_32px_rgba(0,0,0,0.5)]">
        <div className="flex shrink-0 items-center justify-between border-b border-kiosk-industrial-border px-4 py-3">
          <h2 id="usb-storage-title" className="text-lg font-black uppercase tracking-wide text-zinc-100">
            USB storage
          </h2>
          <div className="flex gap-2">
            <KioskButton variant="ghost" className="min-h-10 px-3 text-sm" onClick={onRefresh}>
              Refresh
            </KioskButton>
            <KioskButton variant="secondary" className="min-h-10 px-3 text-sm" onClick={onClose}>
              Close
            </KioskButton>
          </div>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto p-4">
          {error && (
            <p className="mb-3 rounded-xl border border-red-500/40 bg-red-950/40 px-3 py-2 text-sm text-red-200">{error}</p>
          )}

          {volumes.length === 0 ? (
            <p className="text-center text-sm text-zinc-400">
              No removable USB volumes detected. Plug in a USB flash drive, then tap Refresh.
            </p>
          ) : (
            <ul className="flex flex-col gap-2">
              {volumes.map((v) => {
                const isSelected = Boolean(v.mountpoint && selectedMountPath === v.mountpoint);
                const busy = busyDevice === v.device;
                return (
                  <li
                    key={v.device}
                    className={`rounded-2xl border-2 px-3 py-3 ${
                      isSelected
                        ? "border-emerald-500/60 bg-emerald-950/30"
                        : "border-kiosk-industrial-border bg-kiosk-industrial-slate/60"
                    }`}
                  >
                    <div className="flex flex-col gap-1">
                      <p className="font-bold uppercase tracking-wide text-zinc-100">{v.label || v.device}</p>
                      {v.model ? <p className="text-xs text-zinc-500">{v.model}</p> : null}
                      <p className="font-mono text-xs text-zinc-400">{v.device}</p>
                      <p className="text-sm text-zinc-300">
                        {v.mounted && v.mountpoint ? (
                          <>Mounted: {v.mountpoint}</>
                        ) : (
                          <span className="text-amber-400/90">Not mounted</span>
                        )}
                      </p>
                    </div>
                    <div className="mt-3 flex flex-wrap gap-2">
                      {v.mounted && v.mountpoint ? (
                        <KioskButton
                          variant={isSelected ? "primary" : "secondary"}
                          className="min-h-11 flex-1 text-sm"
                          onClick={() => onSelectMount(v.mountpoint!)}
                        >
                          {isSelected ? "Selected" : "Use for save"}
                        </KioskButton>
                      ) : (
                        <KioskButton
                          variant="primary"
                          className="min-h-11 flex-1 text-sm"
                          disabled={busy}
                          onClick={() => mountDevice(v.device)}
                        >
                          {busy ? "Mounting…" : "Mount"}
                        </KioskButton>
                      )}
                    </div>
                  </li>
                );
              })}
            </ul>
          )}
        </div>

        <p className="shrink-0 border-t border-kiosk-industrial-border px-4 py-2 text-center text-[11px] text-zinc-500">
          Scan to USB uses the drive marked &quot;Selected&quot;. Mount requires udisks2 (udisksctl) on the appliance.
        </p>
      </div>
    </div>
  );
}
