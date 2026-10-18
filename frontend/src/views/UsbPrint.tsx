import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { apiUrl, parseErrorDetail } from "../api";
import { KioskButton } from "../components/KioskButton";
import { ProgressBar } from "../components/ProgressBar";
import { StatusModal } from "../components/StatusModal";

interface UsbDriveInfo {
  device: string;
  mountpoint: string | null;
  label: string;
  model: string;
  mounted: boolean;
  fstype: string;
  size: string;
}

interface UsbFileEntry {
  name: string;
  rel_path: string;
  is_dir: boolean;
  ext: string;
  size_bytes: number;
  size_label: string;
  pages: number;
}

type PrintSidesMode = "one_sided" | "two_sided_book" | "two_sided_tablet";
type QualityMode = "draft" | "normal" | "best";
type PaperSizeOption = "A4" | "Letter" | "Legal" | "A5" | "4x6";

const SIDES_CYCLE: readonly PrintSidesMode[] = [
  "one_sided",
  "two_sided_book",
  "two_sided_tablet",
];

const SIDES_META: Record<
  PrintSidesMode,
  { label: string; subtitle: string; duplex: boolean; pageFlip: "long_edge" | "short_edge" }
> = {
  one_sided: {
    label: "1-Sided",
    subtitle: "Single-Sided Print",
    duplex: false,
    pageFlip: "long_edge",
  },
  two_sided_book: {
    label: "2-Sided (Book)",
    subtitle: "Flip on Long Edge",
    duplex: true,
    pageFlip: "long_edge",
  },
  two_sided_tablet: {
    label: "2-Sided (Tablet)",
    subtitle: "Flip on Short Edge",
    duplex: true,
    pageFlip: "short_edge",
  },
};

const QUALITY_CYCLE: readonly QualityMode[] = ["draft", "normal", "best"];
const PAPER_SIZES: readonly PaperSizeOption[] = ["A4", "Letter", "Legal", "A5", "4x6"];

export function UsbPrint() {
  const nav = useNavigate();

  // USB Drives & Folder Navigation
  const [usbDrives, setUsbDrives] = useState<UsbDriveInfo[]>([]);
  const [selectedDevice, setSelectedDevice] = useState<string>("");
  const [loadingDrives, setLoadingDrives] = useState(false);

  const [subpath, setSubpath] = useState<string>("");
  const [entries, setEntries] = useState<UsbFileEntry[]>([]);
  const [loadingFiles, setLoadingFiles] = useState(false);
  const [selectedFile, setSelectedFile] = useState<UsbFileEntry | null>(null);
  const [previewPage, setPreviewPage] = useState<number>(0);

  // Print Options
  const [copies, setCopies] = useState<number>(1);
  const [sidesMode, setSidesMode] = useState<PrintSidesMode>("one_sided");
  const [color, setColor] = useState<boolean>(true);
  const [quality, setQuality] = useState<QualityMode>("normal");
  const [paperSize, setPaperSize] = useState<PaperSizeOption>("A4");
  const [fitToPage, setFitToPage] = useState<boolean>(true);
  const [collate, setCollate] = useState<boolean>(true);

  // Execution state
  const [printing, setPrinting] = useState<boolean>(false);
  const [cancelling, setCancelling] = useState<boolean>(false);
  const [modal, setModal] = useState<{
    title: string;
    message: string;
    variant?: "info" | "error";
  } | null>(null);
  const busyRef = useRef(false);

  const selectedDrive = usbDrives.find((d) => d.device === selectedDevice) ?? null;

  const fetchDrives = useCallback(async () => {
    setLoadingDrives(true);
    try {
      const res = await fetch(apiUrl("/api/scan/usb/drives"));
      if (!res.ok) return;
      const data = await res.json();
      const drives: UsbDriveInfo[] = Array.isArray(data?.drives) ? data.drives : [];
      setUsbDrives(drives);
      setSelectedDevice((prev) => {
        if (prev && drives.some((d) => d.device === prev)) return prev;
        return drives[0]?.device ?? "";
      });
    } catch {
      /* ignore */
    } finally {
      setLoadingDrives(false);
    }
  }, []);

  const fetchFiles = useCallback(
    async (targetDevice: string, targetMount: string | null, folderPath: string) => {
      if (!targetDevice && !targetMount) {
        setEntries([]);
        return;
      }
      setLoadingFiles(true);
      try {
        const params = new URLSearchParams();
        if (targetDevice) params.set("device", targetDevice);
        if (targetMount) params.set("mount_path", targetMount);
        if (folderPath) params.set("subpath", folderPath);

        const res = await fetch(apiUrl(`/api/usb/files?${params.toString()}`));
        if (!res.ok) {
          const detail = await parseErrorDetail(res);
          setModal({ title: "USB Read Error", message: detail, variant: "error" });
          setEntries([]);
          return;
        }
        const data = await res.json();
        setEntries(Array.isArray(data?.entries) ? data.entries : []);
        setSubpath(typeof data?.subpath === "string" ? data.subpath : folderPath);
      } catch (e) {
        setModal({
          title: "Network Error",
          message: e instanceof Error ? e.message : "Failed to read USB files",
          variant: "error",
        });
      } finally {
        setLoadingFiles(false);
      }
    },
    []
  );

  useEffect(() => {
    void fetchDrives();
  }, [fetchDrives]);

  useEffect(() => {
    if (!selectedDevice) {
      setEntries([]);
      setSelectedFile(null);
      return;
    }
    const drv = usbDrives.find((d) => d.device === selectedDevice);
    setSelectedFile(null);
    setSubpath("");
    void fetchFiles(selectedDevice, drv?.mountpoint ?? null, "");
  }, [selectedDevice, usbDrives, fetchFiles]);

  function openFolder(relPath: string) {
    setSelectedFile(null);
    void fetchFiles(selectedDevice, selectedDrive?.mountpoint ?? null, relPath);
  }

  function navigateUpFolder() {
    if (!subpath) return;
    const parts = subpath.split("/").filter(Boolean);
    parts.pop();
    openFolder(parts.join("/"));
  }

  function selectPrintableFile(entry: UsbFileEntry) {
    setSelectedFile(entry);
    setPreviewPage(0);
  }

  async function cancelPrint() {
    if (cancelling) return;
    setCancelling(true);
    try {
      await fetch(apiUrl("/api/copy/cancel"), { method: "POST" });
    } catch {
      /* ignore */
    } finally {
      setCancelling(false);
      setPrinting(false);
      busyRef.current = false;
    }
  }

  async function startPrint() {
    if (!selectedFile || busyRef.current) return;
    busyRef.current = true;
    setPrinting(true);
    const sides = SIDES_META[sidesMode];
    try {
      const res = await fetch(apiUrl("/api/usb/print"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          device: selectedDevice || null,
          mount_path: selectedDrive?.mountpoint ?? null,
          path: selectedFile.rel_path,
          copies,
          duplex: sides.duplex,
          page_flip: sides.pageFlip,
          color,
          paper_size: paperSize,
          collate,
          resize_mode: fitToPage ? "fit_to_page" : "actual",
          quality,
        }),
      });
      if (!res.ok) {
        const detail = await parseErrorDetail(res);
        setModal({ title: "Print Failed", message: detail, variant: "error" });
        return;
      }
      const data = await res.json();
      setModal({
        title: "Print Job Sent",
        message: data.message ?? `Printing ${selectedFile.name}`,
        variant: "info",
      });
    } catch (e) {
      setModal({
        title: "Network Error",
        message: e instanceof Error ? e.message : "Print request failed",
        variant: "error",
      });
    } finally {
      setPrinting(false);
      busyRef.current = false;
    }
  }

  function buildPreviewUrl(file: UsbFileEntry, page: number): string {
    const params = new URLSearchParams();
    params.set("path", file.rel_path);
    params.set("page", String(page));
    if (selectedDevice) params.set("device", selectedDevice);
    if (selectedDrive?.mountpoint) params.set("mount_path", selectedDrive.mountpoint);
    return apiUrl(`/api/usb/preview?${params.toString()}`);
  }

  function fileIcon(entry: UsbFileEntry): string {
    if (entry.is_dir) return "📁";
    if (entry.ext === "pdf") return "📄";
    if (entry.ext === "txt") return "📝";
    return "🖼️";
  }

  return (
    <div className="flex h-[100dvh] w-[100dvw] flex-col overflow-hidden bg-kiosk-industrial-bezel text-zinc-100">
      <header className="flex shrink-0 items-center justify-between gap-2 border-b border-kiosk-industrial-border bg-kiosk-industrial-navy px-3 py-2.5 md:px-6">
        <div className="flex items-center gap-3">
          <button
            type="button"
            disabled={printing}
            onClick={() => {
              if (selectedFile) {
                setSelectedFile(null);
              } else {
                nav("/");
              }
            }}
            className="flex h-11 items-center justify-center rounded-xl border border-kiosk-industrial-border bg-kiosk-industrial-slate px-3.5 text-sm font-black uppercase tracking-wider text-zinc-100 disabled:opacity-40 active:scale-95"
          >
            ← {selectedFile ? "Files" : "Back"}
          </button>
          <div>
            <p className="text-[10px] font-semibold uppercase tracking-wider text-zinc-500">
              HP 9010 USB Print
            </p>
            <h1 className="text-lg font-black uppercase tracking-wide text-zinc-100 md:text-2xl">
              {selectedFile ? selectedFile.name : "Print from USB"}
            </h1>
          </div>
        </div>

        {/* Copies Stepper (shown when a file is selected) */}
        {selectedFile && (
          <div className="flex items-center gap-1.5 rounded-xl border border-kiosk-industrial-border bg-kiosk-industrial-slate/70 px-2.5 py-1.5">
            <span className="mr-1 hidden text-xs font-semibold uppercase tracking-wider text-zinc-400 sm:inline">
              Copies
            </span>
            <button
              type="button"
              disabled={printing || copies <= 1}
              onClick={() => setCopies((c) => Math.max(1, c - 1))}
              className="flex h-9 w-9 items-center justify-center rounded-lg border border-kiosk-industrial-border bg-kiosk-industrial-navy text-xl font-bold text-zinc-100 disabled:opacity-40 active:scale-95"
            >
              −
            </button>
            <span className="min-w-[2.5rem] text-center font-mono text-2xl font-black tabular-nums text-emerald-400">
              {copies}
            </span>
            <button
              type="button"
              disabled={printing || copies >= 99}
              onClick={() => setCopies((c) => Math.min(99, c + 1))}
              className="flex h-9 w-9 items-center justify-center rounded-lg border border-kiosk-industrial-border bg-kiosk-industrial-navy text-xl font-bold text-zinc-100 disabled:opacity-40 active:scale-95"
            >
              +
            </button>
          </div>
        )}
      </header>

      <main className="mx-auto flex min-h-0 w-full max-w-5xl flex-1 flex-col gap-3 overflow-y-auto p-3 md:p-5">
        {printing && (
          <div className="my-auto flex w-full max-w-xl flex-col items-center gap-6 self-center px-2">
            <div className="w-full">
              <ProgressBar
                label={`Printing ${selectedFile?.name ?? "document"} (${copies} ${copies === 1 ? "copy" : "copies"})…`}
                variant="print"
              />
            </div>
            <KioskButton
              variant="industrial"
              className="min-h-[4rem] w-full max-w-xs border-2 border-red-500/70 bg-red-950/60 text-xl font-black uppercase tracking-wider text-red-200 ring-2 ring-red-500/30"
              disabled={cancelling}
              onClick={() => void cancelPrint()}
            >
              {cancelling ? "Stopping…" : "Stop / Cancel"}
            </KioskButton>
          </div>
        )}

        {/* VIEW A: USB Drive & File Browser */}
        {!printing && !selectedFile && (
          <>
            {/* USB Flash Drive Selector */}
            <div className="rounded-2xl border border-kiosk-industrial-border bg-kiosk-industrial-slate/60 p-3 md:p-4">
              <div className="flex items-center justify-between gap-2">
                <label className="block text-xs font-bold uppercase tracking-wider text-zinc-400">
                  USB Flash Drive (Storage Only)
                </label>
                <button
                  type="button"
                  disabled={loadingDrives}
                  onClick={() => void fetchDrives()}
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
                        onClick={() => setSelectedDevice(drive.device)}
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
                            active
                              ? "bg-amber-500 text-black"
                              : "bg-kiosk-industrial-slate text-zinc-400"
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

            {/* Folder & Printable File List */}
            {selectedDevice && (
              <div className="flex min-h-0 flex-1 flex-col rounded-2xl border border-kiosk-industrial-border bg-kiosk-industrial-slate/50 p-3 md:p-4">
                <div className="mb-2.5 flex items-center justify-between gap-2 border-b border-kiosk-industrial-border pb-2">
                  <div className="min-w-0">
                    <p className="text-[10px] font-bold uppercase tracking-wider text-zinc-400">
                      Current Folder
                    </p>
                    <p className="truncate font-mono text-sm font-bold text-amber-300">
                      /{subpath || ""}
                    </p>
                  </div>
                  {subpath && (
                    <button
                      type="button"
                      onClick={navigateUpFolder}
                      className="rounded-xl border border-kiosk-industrial-border bg-kiosk-industrial-navy px-3.5 py-1.5 text-xs font-black uppercase tracking-wider text-zinc-100 active:scale-95"
                    >
                      ⬆ Up Folder
                    </button>
                  )}
                </div>

                {loadingFiles ? (
                  <p className="my-auto text-center text-sm text-zinc-400">
                    Reading USB files…
                  </p>
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
                        onClick={() =>
                          entry.is_dir ? openFolder(entry.rel_path) : selectPrintableFile(entry)
                        }
                        className="flex items-center justify-between gap-3 rounded-xl border border-kiosk-industrial-border bg-kiosk-industrial-navy/80 px-4 py-3 text-left transition hover:border-amber-500/50 active:scale-[0.99]"
                      >
                        <div className="flex min-w-0 items-center gap-3">
                          <span className="text-2xl">{fileIcon(entry)}</span>
                          <div className="min-w-0">
                            <p className="truncate text-sm font-bold text-zinc-100">
                              {entry.name}
                            </p>
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
        )}

        {/* VIEW B: File Preview & Print Options */}
        {!printing && selectedFile && (
          <div className="flex min-h-0 flex-1 flex-col gap-4 md:flex-row md:items-stretch">
            {/* Left: Live File Page Preview */}
            <div className="flex flex-1 flex-col items-center justify-between rounded-2xl border border-kiosk-industrial-border bg-black/50 p-3">
              <div className="flex w-full items-center justify-between px-1 pb-2">
                <span className="truncate text-xs font-bold uppercase tracking-wider text-zinc-400">
                  {selectedFile.name} ({selectedFile.size_label})
                </span>
                <span className="font-mono text-xs font-bold text-amber-400">
                  Page {previewPage + 1} of {Math.max(1, selectedFile.pages)}
                </span>
              </div>

              <div className="flex max-h-[42dvh] min-h-[12rem] w-full flex-1 items-center justify-center overflow-hidden rounded-xl bg-zinc-900/80 p-2 md:max-h-[54dvh]">
                <img
                  src={buildPreviewUrl(selectedFile, previewPage)}
                  alt={`Preview of ${selectedFile.name}`}
                  className="max-h-full max-w-full rounded object-contain shadow-lg"
                />
              </div>

              {selectedFile.pages > 1 && (
                <div className="mt-2 flex items-center gap-3 pt-1">
                  <button
                    type="button"
                    disabled={previewPage <= 0}
                    onClick={() => setPreviewPage((p) => Math.max(0, p - 1))}
                    className="rounded-lg border border-kiosk-industrial-border bg-kiosk-industrial-navy px-3 py-1 text-xs font-bold text-zinc-200 disabled:opacity-30 active:scale-95"
                  >
                    ◀ Prev
                  </button>
                  <span className="font-mono text-xs font-bold text-amber-400">
                    {previewPage + 1} / {selectedFile.pages}
                  </span>
                  <button
                    type="button"
                    disabled={previewPage >= selectedFile.pages - 1}
                    onClick={() =>
                      setPreviewPage((p) => Math.min(selectedFile.pages - 1, p + 1))
                    }
                    className="rounded-lg border border-kiosk-industrial-border bg-kiosk-industrial-navy px-3 py-1 text-xs font-bold text-zinc-200 disabled:opacity-30 active:scale-95"
                  >
                    Next ▶
                  </button>
                </div>
              )}
            </div>

            {/* Right: HP 9010 Print Options & Print Button */}
            <div className="flex flex-col justify-between gap-3 md:w-80">
              <div className="grid grid-cols-2 gap-2">
                {/* Sides */}
                <KioskButton
                  layout="tile"
                  variant="industrial"
                  tileActive={sidesMode !== "one_sided"}
                  className="min-h-[4.75rem]"
                  onClick={() =>
                    setSidesMode((prev) => {
                      const idx = SIDES_CYCLE.indexOf(prev);
                      return SIDES_CYCLE[(idx + 1) % SIDES_CYCLE.length];
                    })
                  }
                >
                  <span className="text-sm">{SIDES_META[sidesMode].label}</span>
                  <span className="mt-0.5 block text-[10px] font-medium normal-case text-zinc-400">
                    {SIDES_META[sidesMode].subtitle}
                  </span>
                </KioskButton>

                {/* Color */}
                <KioskButton
                  layout="tile"
                  variant="industrial"
                  tileActive={color}
                  className="min-h-[4.75rem]"
                  onClick={() => setColor((c) => !c)}
                >
                  <span className="text-sm">{color ? "Color" : "B&W"}</span>
                  <span className="mt-0.5 block text-[10px] font-medium normal-case text-zinc-400">
                    {color ? "Full Color" : "Grayscale"}
                  </span>
                </KioskButton>

                {/* Quality */}
                <KioskButton
                  layout="tile"
                  variant="industrial"
                  tileActive={quality !== "normal"}
                  className="min-h-[4.75rem]"
                  onClick={() =>
                    setQuality((prev) => {
                      const idx = QUALITY_CYCLE.indexOf(prev);
                      return QUALITY_CYCLE[(idx + 1) % QUALITY_CYCLE.length];
                    })
                  }
                >
                  <span className="text-sm uppercase">Quality: {quality}</span>
                  <span className="mt-0.5 block text-[10px] font-medium normal-case text-zinc-400">
                    Tap to cycle
                  </span>
                </KioskButton>

                {/* Paper Size */}
                <KioskButton
                  layout="tile"
                  variant="industrial"
                  tileActive={paperSize !== "A4"}
                  className="min-h-[4.75rem]"
                  onClick={() =>
                    setPaperSize((prev) => {
                      const idx = PAPER_SIZES.indexOf(prev);
                      return PAPER_SIZES[(idx + 1) % PAPER_SIZES.length];
                    })
                  }
                >
                  <span className="text-sm">Paper: {paperSize}</span>
                  <span className="mt-0.5 block text-[10px] font-medium normal-case text-zinc-400">
                    Tap to cycle
                  </span>
                </KioskButton>

                {/* Fit to Page */}
                <KioskButton
                  layout="tile"
                  variant="industrial"
                  tileActive={fitToPage}
                  className="min-h-[4.75rem]"
                  onClick={() => setFitToPage((f) => !f)}
                >
                  <span className="text-sm">{fitToPage ? "Fit to Page" : "Actual 100%"}</span>
                  <span className="mt-0.5 block text-[10px] font-medium normal-case text-zinc-400">
                    Page Scaling
                  </span>
                </KioskButton>

                {/* Collate */}
                <KioskButton
                  layout="tile"
                  variant="industrial"
                  tileActive={collate && copies > 1}
                  className="min-h-[4.75rem]"
                  disabled={copies <= 1}
                  onClick={() => setCollate((c) => !c)}
                >
                  <span className="text-sm">Collate: {collate ? "ON" : "OFF"}</span>
                  <span className="mt-0.5 block text-[10px] font-medium normal-case text-zinc-400">
                    {copies > 1 ? "1-2-3, 1-2-3" : "For 2+ copies"}
                  </span>
                </KioskButton>
              </div>

              <div className="flex flex-col gap-2">
                <KioskButton
                  variant="primary"
                  className="min-h-[4rem] w-full text-xl font-black uppercase tracking-wider"
                  onClick={() => void startPrint()}
                >
                  🖨️ Print ({copies})
                </KioskButton>
                <button
                  type="button"
                  onClick={() => setSelectedFile(null)}
                  className="rounded-xl border border-kiosk-industrial-border bg-kiosk-industrial-navy py-2.5 text-xs font-bold uppercase tracking-wider text-zinc-300 active:scale-95"
                >
                  ← Choose Different File
                </button>
              </div>
            </div>
          </div>
        )}
      </main>

      <StatusModal
        open={modal !== null}
        title={modal?.title ?? ""}
        message={modal?.message ?? ""}
        variant={modal?.variant}
        onClose={() => setModal(null)}
      />
    </div>
  );
}
