import type { UsbDriveInfo } from "../../hooks/useUsbDrives";
import { fileIcon, type UsbFileEntry } from "./usbPrintTypes";

interface UsbFileBrowserProps {
  usbDrives: UsbDriveInfo[];
  selectedDevice: string;
  loadingDrives: boolean;
  subpath: string;
  entries: UsbFileEntry[];
  loadingFiles: boolean;
  onRefreshDrives: () => void;
  onSelectDevice: (device: string) => void;
  onNavigateUp: () => void;
  onOpenFolder: (relPath: string) => void;
  onSelectFile: (entry: UsbFileEntry) => void;
}

export function UsbFileBrowser({
  usbDrives,
  selectedDevice,
  loadingDrives,
  subpath,
  entries,
  loadingFiles,
  onRefreshDrives,
  onSelectDevice,
  onNavigateUp,
  onOpenFolder,
  onSelectFile,
}: UsbFileBrowserProps) {
  return (
    <>
      <div className="rounded-2xl border border-kiosk-industrial-border bg-kiosk-industrial-slate/60 p-3 md:p-4">
        <div className="flex items-center justify-between gap-2">
          <label className="block text-xs font-bold uppercase tracking-wider text-zinc-400">
            USB Flash Drive (Storage Only)
          </label>
          <button
            type="button"
            disabled={loadingDrives}
            onClick={onRefreshDrives}
            className="rounded-lg border border-kiosk-industrial-border bg-kiosk-industrial-navy px-3 py-1 text-xs font-bold uppercase tracking-wider text-amber-300 active:scale-95 disabled:opacity-40"
          >
            {loadingDrives ? "Refreshing…" : "↻ Refresh USB"}
          </button>
        </div>

        {usbDrives.length === 0 ? (
          <div className="mt-2 rounded-xl border border-amber-500/30 bg-amber-950/20 px-4 py-3 text-sm text-amber-200">
            No USB flash drive detected. Insert a FAT32/exFAT USB flash drive and tap{" "}
            <span className="font-bold">↻ Refresh USB</span>.
          </div>
        ) : (
          <div className="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-2">
            {usbDrives.map((drive) => {
              const active = selectedDevice === drive.device;
              return (
                <button
                  key={drive.device}
                  type="button"
                  onClick={() => onSelectDevice(drive.device)}
                  className={`flex items-center justify-between rounded-xl border px-3.5 py-2.5 text-left transition active:scale-[0.99] ${
                    active
                      ? "border-amber-500 bg-amber-500/15 text-zinc-100 ring-1 ring-amber-500/50"
                      : "border-kiosk-industrial-border bg-kiosk-industrial-navy/70 text-zinc-300"
                  }`}
                >
                  <div>
                    <p className="text-sm font-black uppercase tracking-wide text-zinc-100">
                      🔌 {drive.label || "USB Flash Drive"}
                    </p>
                    <p className="text-xs text-zinc-400">
                      {[
                        drive.model,
                        drive.size,
                        drive.fstype ? drive.fstype.toUpperCase() : "",
                        drive.device,
                      ]
                        .filter(Boolean)
                        .join(" • ")}
                    </p>
                  </div>
                  <span
                    className={`rounded-lg px-2 py-0.5 text-[10px] font-bold uppercase ${
                      active ? "bg-amber-500 text-black" : "bg-kiosk-industrial-slate text-zinc-400"
                    }`}
                  >
                    {active ? "Active" : "Select"}
                  </span>
                </button>
              );
            })}
          </div>
        )}
      </div>

      {selectedDevice && (
        <div className="flex min-h-0 flex-1 flex-col rounded-2xl border border-kiosk-industrial-border bg-kiosk-industrial-slate/50 p-3 md:p-4">
          <div className="mb-2.5 flex items-center justify-between gap-2 border-b border-kiosk-industrial-border pb-2">
            <div className="min-w-0">
              <p className="text-[10px] font-bold uppercase tracking-wider text-zinc-400">
                Current Folder
              </p>
              <p className="truncate font-mono text-sm font-bold text-amber-300">/{subpath || ""}</p>
            </div>
            {subpath && (
              <button
                type="button"
                onClick={onNavigateUp}
                className="rounded-xl border border-kiosk-industrial-border bg-kiosk-industrial-navy px-3.5 py-1.5 text-xs font-black uppercase tracking-wider text-zinc-100 active:scale-95"
              >
                ⬆ Up Folder
              </button>
            )}
          </div>

          {loadingFiles ? (
            <p className="my-auto text-center text-sm text-zinc-400">Reading USB files…</p>
          ) : entries.length === 0 ? (
            <p className="my-auto text-center text-sm text-zinc-400">
              No printable files (.pdf, .jpg, .png, .tiff, .txt) found in this folder.
            </p>
          ) : (
            <div className="grid grid-cols-1 gap-2 overflow-y-auto sm:grid-cols-2">
              {entries.map((entry) => (
                <button
                  key={entry.rel_path}
                  type="button"
                  onClick={() => (entry.is_dir ? onOpenFolder(entry.rel_path) : onSelectFile(entry))}
                  className="flex items-center justify-between gap-3 rounded-xl border border-kiosk-industrial-border bg-kiosk-industrial-navy/80 px-4 py-3 text-left transition hover:border-amber-500/50 active:scale-[0.99]"
                >
                  <div className="flex min-w-0 items-center gap-3">
                    <span className="text-2xl">{fileIcon(entry)}</span>
                    <div className="min-w-0">
                      <p className="truncate text-sm font-bold text-zinc-100">{entry.name}</p>
                      <p className="text-xs text-zinc-400">
                        {entry.is_dir
                          ? "Folder — Tap to Open"
                          : `${entry.ext.toUpperCase()} • ${entry.size_label}${
                              entry.pages > 1 ? ` • ${entry.pages} pages` : ""
                            }`}
                      </p>
                    </div>
                  </div>
                  <span className="shrink-0 rounded-lg bg-kiosk-industrial-slate px-2.5 py-1 text-xs font-bold uppercase text-amber-300">
                    {entry.is_dir ? "Open ▶" : "Select ▶"}
                  </span>
                </button>
              ))}
            </div>
          )}
        </div>
      )}
    </>
  );
}
