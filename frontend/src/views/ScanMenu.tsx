import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { apiUrl, parseErrorDetail } from "../api";
import { KioskButton } from "../components/KioskButton";
import { ProgressBar } from "../components/ProgressBar";
import { StatusModal } from "../components/StatusModal";

type ScanDestination = "email" | "usb" | "archive";
type Stage = "idle" | "scanning" | "awaiting_next_page" | "delivering" | "done" | "error";
type ScanFormat = "pdf" | "jpg" | "png" | "tiff";
type ScanQuality = "standard" | "high" | "best";

interface UsbDriveInfo {
  device: string;
  mountpoint: string | null;
  label: string;
  model: string;
  mounted: boolean;
  fstype: string;
  size: string;
}

const FORMAT_CYCLE: readonly ScanFormat[] = ["pdf", "jpg", "png", "tiff"];

const FORMAT_META: Record<ScanFormat, { label: string; subtitle: string }> = {
  pdf: { label: "Format: PDF", subtitle: "Multi-Page Document (.pdf)" },
  jpg: { label: "Format: JPG", subtitle: "Photo / 1 File per Page (.jpg)" },
  png: { label: "Format: PNG", subtitle: "Lossless / 1 File per Page (.png)" },
  tiff: { label: "Format: TIFF", subtitle: "Archival Multi-Page (.tiff)" },
};

const QUALITY_CYCLE: readonly ScanQuality[] = ["standard", "high", "best"];

const QUALITY_META: Record<
  ScanQuality,
  { label: string; subtitle: string; dpi: 150 | 300 | 600 }
> = {
  standard: { label: "Draft (150 DPI)", subtitle: "Smaller File • Fast", dpi: 150 },
  high: { label: "Normal (300 DPI)", subtitle: "Standard Document", dpi: 300 },
  best: { label: "Best (600 DPI)", subtitle: "High Detail", dpi: 600 },
};

const DESTINATION_META: Record<
  ScanDestination,
  { title: string; subtitle: string; actionLabel: string; finishLabel: string }
> = {
  email: {
    title: "Scan to Email",
    subtitle: "HP 9010 Digital Send",
    actionLabel: "Start Scan to Email",
    finishLabel: "Finish & Send Email",
  },
  usb: {
    title: "Scan to USB Drive",
    subtitle: "HP 9010 USB Storage",
    actionLabel: "Start Scan to USB",
    finishLabel: "Finish & Save to USB",
  },
  archive: {
    title: "Scan to Archive",
    subtitle: "HP 9010 Station Folder",
    actionLabel: "Start Scan to Archive",
    finishLabel: "Finish & Save to Archive",
  },
};

export function ScanMenu() {
  const nav = useNavigate();
  const { destination: rawDest } = useParams<{ destination?: string }>();
  const destination: ScanDestination | null =
    rawDest === "email" || rawDest === "usb" || rawDest === "archive" ? rawDest : null;

  // Scan settings
  const [source, setSource] = useState<"flatbed" | "adf">("flatbed");
  const [scanDuplex, setScanDuplex] = useState(false);
  const [color, setColor] = useState(true);
  const [outputFormat, setOutputFormat] = useState<ScanFormat>("pdf");
  const [quality, setQuality] = useState<ScanQuality>("high");
  const [removeBlankPages, setRemoveBlankPages] = useState(false);

  // Destination-specific states
  const [email, setEmail] = useState("");
  const [fileName, setFileName] = useState("");
  const [usbDrives, setUsbDrives] = useState<UsbDriveInfo[]>([]);
  const [selectedUsbDevice, setSelectedUsbDevice] = useState<string>("");
  const [loadingDrives, setLoadingDrives] = useState(false);

  // Multi-step flatbed & preview session state
  const [stage, setStage] = useState<Stage>("idle");
  const [pendingScanId, setPendingScanId] = useState<string | null>(null);
  const [scannedPages, setScannedPages] = useState<number>(0);
  const [previewPage, setPreviewPage] = useState<number>(0);
  const [previewRev, setPreviewRev] = useState<number>(0);
  const [rotatingPreview, setRotatingPreview] = useState<boolean>(false);
  const [cancelling, setCancelling] = useState(false);
  const [modal, setModal] = useState<{ title: string; detail?: string } | null>(null);

  const busyLock = useRef(false);
  const cancelledRef = useRef(false);

  const hardwareBusy = stage === "scanning" || stage === "delivering";
  const currentQuality = QUALITY_META[quality];
  const isMultiStepFlatbed = source === "flatbed";

  const fetchUsbDrives = useCallback(async () => {
    setLoadingDrives(true);
    try {
      const res = await fetch(apiUrl("/api/scan/usb/drives"));
      if (!res.ok) return;
      const data = await res.json();
      const drives: UsbDriveInfo[] = Array.isArray(data?.drives) ? data.drives : [];
      setUsbDrives(drives);
      setSelectedUsbDevice((prev) => {
        if (prev && drives.some((d) => d.device === prev)) return prev;
        return drives[0]?.device ?? "";
      });
    } catch {
      /* ignore */
    } finally {
      setLoadingDrives(false);
    }
  }, []);

  useEffect(() => {
    if (destination === "usb") {
      void fetchUsbDrives();
    }
  }, [destination, fetchUsbDrives]);

  function cycleQuality() {
    setQuality((prev) => {
      const idx = QUALITY_CYCLE.indexOf(prev);
      return QUALITY_CYCLE[(idx + 1) % QUALITY_CYCLE.length];
    });
  }

  async function cancelOperation() {
    if (cancelling) return;
    setCancelling(true);
    cancelledRef.current = true;
    const discardQuery = pendingScanId ? `?scan_id=${encodeURIComponent(pendingScanId)}` : "";
    try {
      await fetch(apiUrl(`/api/copy/cancel${discardQuery}`), { method: "POST" });
    } catch {
      /* ignore */
    } finally {
      setCancelling(false);
      setPendingScanId(null);
      setScannedPages(0);
      setPreviewPage(0);
      setStage("idle");
      busyLock.current = false;
    }
  }

  async function rotateCurrentPreviewPage() {
    if (!pendingScanId || rotatingPreview) return;
    setRotatingPreview(true);
    try {
      const res = await fetch(
        apiUrl(`/api/copy/preview/${encodeURIComponent(pendingScanId)}/rotate?page=${previewPage}`),
        { method: "POST" }
      );
      if (res.ok) {
        setPreviewRev((r) => r + 1);
      }
    } catch {
      /* ignore */
    } finally {
      setRotatingPreview(false);
    }
  }

  function validateDestinationInputs(): boolean {
    if (destination === "email") {
      const trimmed = email.trim();
      if (!trimmed || !trimmed.includes("@")) {
        setModal({
          title: "Email Required",
          detail: "Please enter a valid recipient email address before scanning.",
        });
        return false;
      }
    } else if (destination === "usb") {
      if (!selectedUsbDevice || usbDrives.length === 0) {
        setModal({
          title: "Select a USB Flash Drive",
          detail:
            "No USB storage drive is selected. Plug in a FAT32 or exFAT USB flash drive and tap Refresh.",
        });
        return false;
      }
    }
    return true;
  }

  async function runDeliverStep(scanIdToDeliver: string | null) {
    if (!destination || cancelledRef.current) return;
    if (!validateDestinationInputs()) return;

    busyLock.current = true;
    setStage("delivering");

    const effectiveSource =
      source === "flatbed" ? "flatbed" : scanDuplex ? "adf_duplex" : "adf";

    const selectedDrive = usbDrives.find((d) => d.device === selectedUsbDevice);
    const endpoint =
      destination === "email"
        ? "/api/scan/email"
        : destination === "usb"
          ? "/api/scan/usb"
          : "/api/scan/archive";

    const payload: Record<string, unknown> = {
      scan_id: scanIdToDeliver,
      filename: fileName.trim() || null,
      duplex: source === "adf" ? scanDuplex : false,
      source: effectiveSource,
      color,
      resolution: quality,
      output_format: outputFormat,
      remove_blank_pages: outputFormat === "pdf" ? removeBlankPages : false,
    };

    if (destination === "email") {
      payload.recipient = email.trim();
    } else if (destination === "usb") {
      payload.device = selectedDrive?.device ?? selectedUsbDevice;
      payload.mount_path = selectedDrive?.mountpoint ?? null;
    }

    try {
      const res = await fetch(apiUrl(endpoint), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (cancelledRef.current) return;
      if (!res.ok) {
        const detail = await parseErrorDetail(res);
        setStage(scanIdToDeliver ? "awaiting_next_page" : "idle");
        setModal({ title: "Scan Delivery Failed", detail });
        busyLock.current = false;
        return;
      }
      const data = await res.json();
      setPendingScanId(null);
      setScannedPages(0);
      setPreviewPage(0);
      setStage("idle");
      busyLock.current = false;
      setModal({
        title:
          destination === "email"
            ? "Email Sent"
            : destination === "usb"
              ? "Saved to USB Drive"
              : "Saved to Archive",
        detail: data.message ?? "Scan completed successfully.",
      });
    } catch (e) {
      if (cancelledRef.current) return;
      setStage(scanIdToDeliver ? "awaiting_next_page" : "idle");
      setModal({
        title: "Network Error",
        detail: e instanceof Error ? e.message : "Request failed",
      });
      busyLock.current = false;
    }
  }

  async function runScanPageStep(appendToScanId?: string | null, forcePreview?: boolean) {
    if (busyLock.current || !destination) return;
    if (!validateDestinationInputs()) return;

    busyLock.current = true;
    cancelledRef.current = false;
    setStage("scanning");

    const effectiveSource =
      source === "flatbed" ? "flatbed" : scanDuplex ? "adf_duplex" : "adf";
    const effectiveDuplex = source === "flatbed" ? false : scanDuplex;

    let scanId: string;
    let totalPages = 1;
    try {
      const scanRes = await fetch(apiUrl("/api/scan"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          duplex: effectiveDuplex,
          color,
          resolution_dpi: currentQuality.dpi,
          source: effectiveSource,
          original_size: "A4",
          lighter_darker: 0,
          content_type: "mixed",
          resize_mode: "actual",
          resize_percent: 100,
          append_to_scan_id: appendToScanId ?? null,
        }),
      });
      if (cancelledRef.current) return;
      if (!scanRes.ok) {
        const detail = await parseErrorDetail(scanRes);
        setStage(appendToScanId ? "awaiting_next_page" : "idle");
        setModal({ title: "Scan Failed", detail });
        busyLock.current = false;
        return;
      }
      const data = await scanRes.json();
      if (data.cancelled || cancelledRef.current) {
        setStage("idle");
        busyLock.current = false;
        return;
      }
      scanId = data.scan_id as string;
      totalPages = typeof data.pages === "number" ? data.pages : scannedPages + 1;
      setPendingScanId(scanId);
      setScannedPages(totalPages);
      setPreviewPage(Math.max(0, totalPages - 1));
      setPreviewRev((r) => r + 1);
    } catch (e) {
      if (cancelledRef.current) return;
      setStage(appendToScanId ? "awaiting_next_page" : "idle");
      setModal({
        title: "Network Error",
        detail: e instanceof Error ? e.message : "Scan failed",
      });
      busyLock.current = false;
      return;
    }

    // Flatbed multi-step or explicit Preview always pauses at the interactive preview screen
    if (isMultiStepFlatbed || forcePreview) {
      setStage("awaiting_next_page");
      busyLock.current = false;
      return;
    }

    await runDeliverStep(scanId);
  }

  // ============================================================================
  // VIEW 1: Main Scan Menu (/scan) — Destination Selection Only (No Email Input!)
  // ============================================================================
  if (!destination) {
    return (
      <div className="flex h-[100dvh] w-[100dvw] flex-col overflow-hidden bg-kiosk-industrial-bezel text-zinc-100">
        <header className="flex shrink-0 items-center justify-between border-b border-kiosk-industrial-border bg-kiosk-industrial-navy px-4 py-3 md:px-8">
          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={() => nav("/")}
              className="flex h-11 items-center justify-center rounded-xl border border-kiosk-industrial-border bg-kiosk-industrial-slate px-3.5 text-sm font-black uppercase tracking-wider text-zinc-100 active:scale-95"
            >
              ← Back
            </button>
            <div>
              <p className="text-xs font-semibold uppercase tracking-wider text-zinc-500">
                HP 9010 Scanner
              </p>
              <h1 className="text-xl font-black uppercase tracking-wide text-zinc-100 md:text-2xl">
                Scan — Select Destination
              </h1>
            </div>
          </div>
        </header>

        <main className="mx-auto flex min-h-0 w-full max-w-5xl flex-1 flex-col justify-center gap-4 p-4 md:grid md:grid-cols-3 md:items-stretch md:gap-6 md:p-8">
          <KioskButton
            layout="tile"
            variant="industrial"
            className="min-h-[9rem] md:min-h-[16rem]"
            onClick={() => nav("/scan/email")}
          >
            <span className="text-3xl md:text-4xl">📧</span>
            <span className="mt-2 block text-xl font-black uppercase tracking-wide md:text-2xl">
              Scan to Email
            </span>
            <span className="mt-1.5 block text-xs font-medium normal-case tracking-normal text-zinc-400">
              Enter recipient address, preview pages, and send PDF or JPG via email
            </span>
          </KioskButton>

          <KioskButton
            layout="tile"
            variant="industrial"
            className="min-h-[9rem] md:min-h-[16rem]"
            onClick={() => nav("/scan/usb")}
          >
            <span className="text-3xl md:text-4xl">🔌</span>
            <span className="mt-2 block text-xl font-black uppercase tracking-wide md:text-2xl">
              Scan to USB
            </span>
            <span className="mt-1.5 block text-xs font-medium normal-case tracking-normal text-zinc-400">
              Choose a connected USB flash drive and save scanned documents directly
            </span>
          </KioskButton>

          <KioskButton
            layout="tile"
            variant="industrial"
            className="min-h-[9rem] md:min-h-[16rem]"
            onClick={() => nav("/scan/archive")}
          >
            <span className="text-3xl md:text-4xl">📁</span>
            <span className="mt-2 block text-xl font-black uppercase tracking-wide md:text-2xl">
              Scan to Archive
            </span>
            <span className="mt-1.5 block text-xs font-medium normal-case tracking-normal text-zinc-400">
              Save scanned documents directly to the station archive folder
            </span>
          </KioskButton>
        </main>
      </div>
    );
  }

  // ============================================================================
  // VIEW 2: Destination-Specific Scan Page (/scan/email, /scan/usb, /scan/archive)
  // ============================================================================
  const destMeta = DESTINATION_META[destination];

  return (
    <div className="flex h-[100dvh] w-[100dvw] flex-col overflow-hidden bg-kiosk-industrial-bezel text-zinc-100">
      <header className="flex shrink-0 items-center justify-between gap-2 border-b border-kiosk-industrial-border bg-kiosk-industrial-navy px-3 py-2.5 md:px-6">
        <div className="flex items-center gap-3">
          <button
            type="button"
            disabled={hardwareBusy}
            onClick={() => {
              if (pendingScanId) {
                void cancelOperation();
              }
              nav("/scan");
            }}
            className="flex h-11 items-center justify-center rounded-xl border border-kiosk-industrial-border bg-kiosk-industrial-slate px-3.5 text-sm font-black uppercase tracking-wider text-zinc-100 disabled:opacity-40 active:scale-95"
          >
            ← Back
          </button>
          <div>
            <p className="text-[10px] font-semibold uppercase tracking-wider text-zinc-500">
              {destMeta.subtitle}
            </p>
            <h1 className="text-lg font-black uppercase tracking-wide text-zinc-100 md:text-2xl">
              {destMeta.title}
            </h1>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {stage === "idle" && (
            <button
              type="button"
              disabled={hardwareBusy}
              onClick={() => void runScanPageStep(null, true)}
              className="flex h-11 items-center gap-1.5 rounded-xl border border-amber-500/40 bg-amber-500/15 px-3.5 text-xs font-black uppercase tracking-wider text-amber-300 disabled:opacity-40 active:scale-95"
              title="Scan and preview before saving or sending"
            >
              🔍 Preview
            </button>
          )}
        </div>
      </header>

      <main className="mx-auto flex min-h-0 w-full max-w-5xl flex-1 flex-col justify-between gap-3 overflow-y-auto p-3 md:p-5">
        {/* Active Scanning / Delivering Progress */}
        {(stage === "scanning" || stage === "delivering") && (
          <div className="my-auto flex w-full max-w-xl flex-col items-center gap-6 self-center px-2">
            <div className="w-full">
              <ProgressBar
                label={
                  stage === "delivering"
                    ? destination === "email"
                      ? "Sending Email…"
                      : destination === "usb"
                        ? "Saving to USB Flash Drive…"
                        : "Saving to Archive…"
                    : isMultiStepFlatbed
                      ? `Scanning Page ${scannedPages + 1} from Flatbed…`
                      : "Scanning Document…"
                }
                variant="scan"
              />
            </div>
            <KioskButton
              variant="industrial"
              className="min-h-[4rem] w-full max-w-xs border-2 border-red-500/70 bg-red-950/60 text-xl font-black uppercase tracking-wider text-red-200 ring-2 ring-red-500/30"
              disabled={cancelling}
              onClick={() => void cancelOperation()}
            >
              {cancelling ? "Stopping…" : "Stop / Cancel"}
            </KioskButton>
          </div>
        )}

        {/* Multi-Step Flatbed & Live Page Preview Modal */}
        {stage === "awaiting_next_page" && pendingScanId && (
          <div className="my-auto flex max-h-full w-full max-w-4xl flex-col gap-4 self-center rounded-3xl border-2 border-amber-500/50 bg-kiosk-industrial-slate/95 p-4 shadow-2xl md:flex-row md:items-stretch md:p-6">
            <div className="flex flex-1 flex-col items-center justify-between rounded-2xl border border-kiosk-industrial-border bg-black/50 p-3">
              <div className="flex w-full items-center justify-between px-1 pb-2">
                <span className="text-xs font-bold uppercase tracking-wider text-zinc-400">
                  Page {previewPage + 1} of {scannedPages}
                </span>
                <button
                  type="button"
                  disabled={rotatingPreview}
                  onClick={() => void rotateCurrentPreviewPage()}
                  className="rounded-lg border border-kiosk-industrial-border bg-kiosk-industrial-navy px-3 py-1 text-xs font-bold uppercase tracking-wider text-zinc-200 active:scale-95 disabled:opacity-40"
                >
                  {rotatingPreview ? "Rotating…" : "↻ Rotate 90°"}
                </button>
              </div>

              <div className="flex max-h-[42dvh] min-h-[12rem] w-full flex-1 items-center justify-center overflow-hidden rounded-xl bg-zinc-900/80 p-2 md:max-h-[50dvh]">
                <img
                  src={apiUrl(
                    `/api/copy/preview/${encodeURIComponent(pendingScanId)}?page=${previewPage}&r=${previewRev}`
                  )}
                  alt={`Scanned page ${previewPage + 1}`}
                  className="max-h-full max-w-full rounded object-contain shadow-lg"
                />
              </div>

              {scannedPages > 1 && (
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
                    {previewPage + 1} / {scannedPages}
                  </span>
                  <button
                    type="button"
                    disabled={previewPage >= scannedPages - 1}
                    onClick={() => setPreviewPage((p) => Math.min(scannedPages - 1, p + 1))}
                    className="rounded-lg border border-kiosk-industrial-border bg-kiosk-industrial-navy px-3 py-1 text-xs font-bold text-zinc-200 disabled:opacity-30 active:scale-95"
                  >
                    Next ▶
                  </button>
                </div>
              )}
            </div>

            <div className="flex flex-col justify-between gap-3 md:w-72">
              <div>
                <p className="text-xs font-bold uppercase tracking-widest text-amber-400">
                  {destMeta.title} Preview
                </p>
                <h2 className="mt-1 text-2xl font-black text-zinc-100">
                  {scannedPages} {scannedPages === 1 ? "Page" : "Pages"} Scanned
                </h2>
                <p className="mt-2 text-sm leading-snug text-zinc-300">
                  {source === "flatbed"
                    ? outputFormat === "jpg" || outputFormat === "png"
                      ? "Place the next page on the glass to add another page (saved as sequentially numbered files), or tap Finish below."
                      : "Place the next page (or flip the document) on the scanner glass to add another page, or tap Finish below."
                    : "Review the scanned document pages before delivering."}
                </p>
              </div>

              <div className="flex flex-col gap-2.5">
                {source === "flatbed" && (
                  <KioskButton
                    variant="industrial"
                    className="min-h-[3.75rem] w-full text-base ring-1 ring-amber-500/40"
                    onClick={() => void runScanPageStep(pendingScanId, true)}
                  >
                    + Scan Page {scannedPages + 1}
                  </KioskButton>
                )}
                <KioskButton
                  variant="primary"
                  className="min-h-[4rem] w-full text-lg"
                  onClick={() => void runDeliverStep(pendingScanId)}
                >
                  {destMeta.finishLabel}
                </KioskButton>
                <button
                  type="button"
                  onClick={() => void cancelOperation()}
                  className="mt-1 rounded-xl border border-red-500/40 bg-red-950/40 py-2.5 text-sm font-bold uppercase tracking-wider text-red-300 active:scale-95"
                >
                  Cancel Scan
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Idle Configuration & Action Screen */}
        {stage === "idle" && (
          <>
            {/* 1. Destination-Specific Header & File Name Box */}
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
                      onChange={(e) => setEmail(e.target.value)}
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
                        onChange={(e) => setFileName(e.target.value)}
                        disabled={hardwareBusy}
                        placeholder="scan (leave blank for default)"
                        className="w-full bg-transparent px-4 py-2.5 text-base text-white placeholder:text-zinc-500 focus:outline-none disabled:opacity-50"
                      />
                      <span className="shrink-0 pr-3 font-mono text-xs font-bold uppercase text-amber-400">
                        .{outputFormat}
                      </span>
                    </div>
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
                      onClick={() => void fetchUsbDrives()}
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
                            onClick={() => setSelectedUsbDevice(drive.device)}
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
                                active
                                  ? "bg-amber-500 text-black"
                                  : "bg-kiosk-industrial-slate text-zinc-400"
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
                        onChange={(e) => setFileName(e.target.value)}
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
                        onChange={(e) => setFileName(e.target.value)}
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

            {/* 2. Scan Settings Grid (Clearly separated from the bottom primary action button) */}
            <div className="grid flex-1 grid-cols-2 gap-2.5 sm:grid-cols-3 md:gap-3">
              {/* Source: Flatbed vs ADF */}
              <KioskButton
                layout="tile"
                variant="industrial"
                tileActive={source === "adf"}
                className="min-h-[5.5rem]"
                disabled={hardwareBusy}
                onClick={() => setSource((s) => (s === "flatbed" ? "adf" : "flatbed"))}
              >
                <span>Source: {source === "flatbed" ? "Flatbed" : "ADF"}</span>
                <span className="mt-1 block text-[11px] font-medium normal-case tracking-normal text-zinc-400">
                  {source === "flatbed"
                    ? "Step-by-Step Scanner Glass"
                    : "Automatic Document Feeder"}
                </span>
              </KioskButton>

              {/* Original Sides: 1-Sided vs 2-Sided */}
              <KioskButton
                layout="tile"
                variant="industrial"
                tileActive={scanDuplex}
                className="min-h-[5.5rem]"
                disabled={hardwareBusy || source === "flatbed"}
                onClick={() => setScanDuplex((d) => !d)}
              >
                <span>{source === "flatbed" ? "Multi-Step Glass" : scanDuplex ? "2-Sided" : "1-Sided"}</span>
                <span className="mt-1 block text-[11px] font-medium normal-case tracking-normal text-zinc-400">
                  {source === "flatbed"
                    ? "Add pages one by one after scan"
                    : scanDuplex
                      ? "Duplex ADF (Both Sides)"
                      : "Single-Sided ADF"}
                </span>
              </KioskButton>

              {/* Color Mode */}
              <KioskButton
                layout="tile"
                variant="industrial"
                tileActive={color}
                className="min-h-[5.5rem]"
                disabled={hardwareBusy}
                onClick={() => setColor((c) => !c)}
              >
                <span>{color ? "Color" : "B&W"}</span>
                <span className="mt-1 block text-[11px] font-medium normal-case tracking-normal text-zinc-400">
                  {color ? "Full Color Scan" : "Grayscale Scan"}
                </span>
              </KioskButton>

              {/* File Type: cycles PDF -> JPG -> PNG -> TIFF */}
              <KioskButton
                layout="tile"
                variant="industrial"
                tileActive={outputFormat !== "pdf"}
                className="min-h-[5.5rem]"
                disabled={hardwareBusy}
                onClick={() =>
                  setOutputFormat((fmt) => {
                    const idx = FORMAT_CYCLE.indexOf(fmt);
                    const next = FORMAT_CYCLE[(idx + 1) % FORMAT_CYCLE.length];
                    if (next !== "pdf") setRemoveBlankPages(false);
                    return next;
                  })
                }
              >
                <span>{FORMAT_META[outputFormat].label}</span>
                <span className="mt-1 block text-[11px] font-medium normal-case tracking-normal text-zinc-400">
                  {FORMAT_META[outputFormat].subtitle}
                </span>
              </KioskButton>

              {/* Resolution / Quality */}
              <KioskButton
                layout="tile"
                variant="industrial"
                tileActive={quality !== "high"}
                className="min-h-[5.5rem]"
                disabled={hardwareBusy}
                onClick={cycleQuality}
              >
                <span>{currentQuality.label}</span>
                <span className="mt-1 block text-[11px] font-medium normal-case tracking-normal text-zinc-400">
                  {currentQuality.subtitle}
                </span>
              </KioskButton>

              {/* Blank Page Removal */}
              <KioskButton
                layout="tile"
                variant="industrial"
                tileActive={removeBlankPages && outputFormat === "pdf"}
                className="min-h-[5.5rem]"
                disabled={hardwareBusy || outputFormat !== "pdf"}
                onClick={() => setRemoveBlankPages((v) => !v)}
              >
                <span>
                  Skip Blank: {outputFormat === "pdf" && removeBlankPages ? "ON" : "OFF"}
                </span>
                <span className="mt-1 block text-[11px] font-medium normal-case tracking-normal text-zinc-400">
                  {outputFormat === "pdf"
                    ? "Auto-remove empty pages"
                    : "Available for PDF only"}
                </span>
              </KioskButton>
            </div>

            {/* 3. Dedicated Primary Action Footer Bar */}
            <div className="flex shrink-0 items-center justify-end gap-3 border-t border-kiosk-industrial-border pt-2.5">
              <KioskButton
                variant="primary"
                className="min-h-[4rem] w-full text-xl font-black uppercase tracking-wider"
                disabled={hardwareBusy}
                onClick={() => void runScanPageStep(null, false)}
              >
                {source === "flatbed"
                  ? `Scan Page 1 (${destMeta.title})`
                  : destMeta.actionLabel}
              </KioskButton>
            </div>
          </>
        )}
      </main>

      <StatusModal
        open={modal !== null}
        title={modal?.title ?? ""}
        message={modal?.detail ?? ""}
        onClose={() => setModal(null)}
      />
    </div>
  );
}
