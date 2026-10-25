import type { UsbDriveInfo } from "../../hooks/useUsbDrives";
import type { ScanDestination, ScanFormat } from "./scanTypes";

interface ScanDestinationHeaderProps {
  destination: ScanDestination;
  hardwareBusy: boolean;
  outputFormat: ScanFormat;
  email: string;
  emailSubject: string;
  emailBody: string;
  fileName: string;
  usbDrives: UsbDriveInfo[];
  selectedUsbDevice: string;
  loadingDrives: boolean;
  onEmailChange: (val: string) => void;
  onEmailSubjectChange: (val: string) => void;
  onEmailBodyChange: (val: string) => void;
  onFileNameChange: (val: string) => void;
  onRefreshUsbDrives: () => void;
  onSelectUsbDevice: (device: string) => void;
}

export function ScanDestinationHeader({
  destination,
  hardwareBusy,
  outputFormat,
  email,
  emailSubject,
  emailBody,
  fileName,
  usbDrives,
  selectedUsbDevice,
  loadingDrives,
  onEmailChange,
  onEmailSubjectChange,
  onEmailBodyChange,
  onFileNameChange,
  onRefreshUsbDrives,
  onSelectUsbDevice,
}: ScanDestinationHeaderProps) {
  return (
    <div className="flex flex-col gap-2.5 rounded-2xl border border-kiosk-industrial-border bg-kiosk-industrial-slate/60 p-3 md:p-4">
      {destination === "email" && (
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
          <div>
            <label className="block text-xs font-bold uppercase tracking-wider text-zinc-400">
              Recipient Email Address
            </label>
            <input
              type="email"
              value={email}
              onChange={(e) => onEmailChange(e.target.value)}
              disabled={hardwareBusy}
              placeholder="recipient@example.com"
              className="mt-1.5 w-full rounded-xl border border-kiosk-industrial-border bg-kiosk-industrial-navy px-4 py-2.5 text-base text-white placeholder:text-zinc-500 focus:border-amber-500 focus:outline-none disabled:opacity-50"
            />
          </div>
          <div>
            <label className="block text-xs font-bold uppercase tracking-wider text-zinc-400">
              File Name (Optional)
            </label>
            <div className="mt-1.5 flex items-center rounded-xl border border-kiosk-industrial-border bg-kiosk-industrial-navy focus-within:border-amber-500">
              <input
                type="text"
                value={fileName}
                onChange={(e) => onFileNameChange(e.target.value)}
                disabled={hardwareBusy}
                placeholder="scan (leave blank for default)"
                className="w-full bg-transparent px-4 py-2.5 text-base text-white placeholder:text-zinc-500 focus:outline-none disabled:opacity-50"
              />
              <span className="shrink-0 pr-3 font-mono text-xs font-bold uppercase text-amber-400">
                .{outputFormat}
              </span>
            </div>
          </div>
          <div>
            <label className="block text-xs font-bold uppercase tracking-wider text-zinc-400">
              Subject (Optional)
            </label>
            <input
              type="text"
              value={emailSubject}
              onChange={(e) => onEmailSubjectChange(e.target.value)}
              disabled={hardwareBusy}
              placeholder="Scan: <filename> (auto)"
              className="mt-1.5 w-full rounded-xl border border-kiosk-industrial-border bg-kiosk-industrial-navy px-4 py-2.5 text-base text-white placeholder:text-zinc-500 focus:border-amber-500 focus:outline-none disabled:opacity-50"
            />
          </div>
          <div>
            <label className="block text-xs font-bold uppercase tracking-wider text-zinc-400">
              Message Body (Optional)
            </label>
            <input
              type="text"
              value={emailBody}
              onChange={(e) => onEmailBodyChange(e.target.value)}
              disabled={hardwareBusy}
              placeholder="Attached is your scanned document from Kopi."
              className="mt-1.5 w-full rounded-xl border border-kiosk-industrial-border bg-kiosk-industrial-navy px-4 py-2.5 text-base text-white placeholder:text-zinc-500 focus:border-amber-500 focus:outline-none disabled:opacity-50"
            />
          </div>
        </div>
      )}

      {destination === "usb" && (
        <>
          <div className="flex items-center justify-between gap-2">
            <label className="block text-xs font-bold uppercase tracking-wider text-zinc-400">
              Select Target USB Flash Drive (Storage Only)
            </label>
            <button
              type="button"
              disabled={loadingDrives || hardwareBusy}
              onClick={onRefreshUsbDrives}
              className="rounded-lg border border-kiosk-industrial-border bg-kiosk-industrial-navy px-3 py-1 text-xs font-bold uppercase tracking-wider text-amber-300 active:scale-95 disabled:opacity-40"
            >
              {loadingDrives ? "Refreshing…" : "↻ Refresh USB"}
            </button>
          </div>

          {usbDrives.length === 0 ? (
            <div className="rounded-xl border border-amber-500/30 bg-amber-950/20 px-4 py-2.5 text-sm text-amber-200">
              No USB flash drive detected. Insert a FAT32/exFAT USB storage drive and tap{" "}
              <span className="font-bold">↻ Refresh USB</span>.
            </div>
          ) : (
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
              {usbDrives.map((drive) => {
                const active = selectedUsbDevice === drive.device;
                return (
                  <button
                    key={drive.device}
                    type="button"
                    onClick={() => onSelectUsbDevice(drive.device)}
                    className={`flex items-center justify-between rounded-xl border px-3.5 py-2 text-left transition active:scale-[0.99] ${
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
                      {active ? "Selected" : "Select"}
                    </span>
                  </button>
                );
              })}
            </div>
          )}

          <div>
            <label className="block text-xs font-bold uppercase tracking-wider text-zinc-400">
              File Name (Optional)
            </label>
            <div className="mt-1 flex items-center rounded-xl border border-kiosk-industrial-border bg-kiosk-industrial-navy focus-within:border-amber-500">
              <input
                type="text"
                value={fileName}
                onChange={(e) => onFileNameChange(e.target.value)}
                disabled={hardwareBusy}
                placeholder="scan_YYYYMMDD_HHMMSS (leave blank for auto timestamp)"
                className="w-full bg-transparent px-4 py-2 text-base text-white placeholder:text-zinc-500 focus:outline-none disabled:opacity-50"
              />
              <span className="shrink-0 pr-3 font-mono text-xs font-bold uppercase text-amber-400">
                .{outputFormat}
              </span>
            </div>
          </div>
        </>
      )}

      {destination === "archive" && (
        <div className="grid grid-cols-1 items-center gap-3 md:grid-cols-2">
          <div>
            <p className="text-xs font-bold uppercase tracking-wider text-zinc-400">
              Archive Destination
            </p>
            <p className="mt-0.5 text-sm text-zinc-300">
              Saved to the station archive folder. Duplicate names automatically append{" "}
              <span className="font-mono text-xs text-zinc-200">-1, -2</span>.
            </p>
          </div>
          <div>
            <label className="block text-xs font-bold uppercase tracking-wider text-zinc-400">
              File Name (Optional)
            </label>
            <div className="mt-1 flex items-center rounded-xl border border-kiosk-industrial-border bg-kiosk-industrial-navy focus-within:border-amber-500">
              <input
                type="text"
                value={fileName}
                onChange={(e) => onFileNameChange(e.target.value)}
                disabled={hardwareBusy}
                placeholder="scan_YYYYMMDD_HHMMSS (leave blank for auto timestamp)"
                className="w-full bg-transparent px-4 py-2.5 text-base text-white placeholder:text-zinc-500 focus:outline-none disabled:opacity-50"
              />
              <span className="shrink-0 pr-3 font-mono text-xs font-bold uppercase text-amber-400">
                .{outputFormat}
              </span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
