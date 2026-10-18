import type { CSSProperties } from "react";
import { useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { apiUrl, parseErrorDetail } from "../api";
import { KioskButton } from "../components/KioskButton";
import { ProgressBar } from "../components/ProgressBar";

type Stage = "idle" | "scanning" | "awaiting_next_page" | "printing" | "done" | "error";

type SidedMode = "1_to_1" | "1_to_2" | "2_to_2" | "2_to_1";
type QualityMode = "draft" | "normal" | "best";
type ResizeMode = "actual" | "fit_to_page" | "full_page_91" | "two_on_one" | "custom";
type PaperSizeOption = "A4" | "Letter" | "Legal" | "A5" | "4x6";
type PageFlipMode = "long_edge" | "short_edge";
type ContentTypeMode = "mixed" | "text" | "photo";

const SIDED_CYCLE: readonly SidedMode[] = ["1_to_1", "1_to_2", "2_to_2", "2_to_1"];
const QUALITY_CYCLE: readonly QualityMode[] = ["draft", "normal", "best"];
const PAPER_SIZES: readonly PaperSizeOption[] = ["A4", "Letter", "Legal", "A5", "4x6"];

const SIDED_META: Record<
  SidedMode,
  { title: string; subtitle: string; scanDuplex: boolean; printDuplex: boolean }
> = {
  "1_to_1": {
    title: "1 → 1 Sided",
    subtitle: "Single Scan → Single Print",
    scanDuplex: false,
    printDuplex: false,
  },
  "1_to_2": {
    title: "1 → 2 Sided",
    subtitle: "Single Scan → Duplex Print",
    scanDuplex: false,
    printDuplex: true,
  },
  "2_to_2": {
    title: "2 → 2 Sided",
    subtitle: "Duplex Scan → Duplex Print",
    scanDuplex: true,
    printDuplex: true,
  },
  "2_to_1": {
    title: "2 → 1 Sided",
    subtitle: "Duplex Scan → Single Print",
    scanDuplex: true,
    printDuplex: false,
  },
};

const QUALITY_META: Record<QualityMode, { label: string; subtitle: string; dpi: 150 | 300 | 600 }> = {
  draft: { label: "Draft", subtitle: "Fast • 150 DPI", dpi: 150 },
  normal: { label: "Normal", subtitle: "Standard • 300 DPI", dpi: 300 },
  best: { label: "Best", subtitle: "High Detail • 600 DPI", dpi: 600 },
};

const RESIZE_LABELS: Record<ResizeMode, string> = {
  actual: "Actual (100%)",
  fit_to_page: "Fit to Page",
  full_page_91: "Full Page (91%)",
  two_on_one: "2 Pages on 1 Sheet",
  custom: "Custom %",
};

const GRID_STYLE: CSSProperties = {
  width: "min(92vw, calc((100dvh - 10rem) * 3 / 2))",
  height:
    "min(calc(100dvh - 10rem), calc(min(92vw, (100dvh - 10rem) * 3 / 2) * 2 / 3))",
};

interface CopyDefaultsPayload {
  sided_mode: SidedMode;
  color: boolean;
  source: "flatbed" | "adf";
  quality: QualityMode;
  lighter_darker: number;
  resize_mode: ResizeMode;
  resize_percent: number;
  original_size: PaperSizeOption;
  paper_size: PaperSizeOption;
  page_flip: PageFlipMode;
  collate: boolean;
  content_type: ContentTypeMode;
}

const FACTORY_DEFAULTS: CopyDefaultsPayload = {
  sided_mode: "1_to_1",
  color: true,
  source: "flatbed",
  quality: "normal",
  lighter_darker: 0,
  resize_mode: "actual",
  resize_percent: 100,
  original_size: "A4",
  paper_size: "A4",
  page_flip: "long_edge",
  collate: true,
  content_type: "mixed",
};

export function CopyMenu() {
  const nav = useNavigate();
  const { mode: rawMode } = useParams<{ mode?: string }>();
  const copyMode: "document" | "photo" | null =
    rawMode === "document" || rawMode === "photo" ? rawMode : null;

  const [copies, setCopies] = useState(1);
  const [sidedMode, setSidedMode] = useState<SidedMode>(FACTORY_DEFAULTS.sided_mode);
  const [color, setColor] = useState(FACTORY_DEFAULTS.color);
  const [source, setSource] = useState<"flatbed" | "adf">(FACTORY_DEFAULTS.source);
  const [quality, setQuality] = useState<QualityMode>(FACTORY_DEFAULTS.quality);

  // Advanced HP 9010 Copy Settings
  const [lighterDarker, setLighterDarker] = useState<number>(FACTORY_DEFAULTS.lighter_darker);
  const [resizeMode, setResizeMode] = useState<ResizeMode>(FACTORY_DEFAULTS.resize_mode);
  const [resizePercent, setResizePercent] = useState<number>(FACTORY_DEFAULTS.resize_percent);
  const [originalSize, setOriginalSize] = useState<PaperSizeOption>(FACTORY_DEFAULTS.original_size);
  const [paperSize, setPaperSize] = useState<PaperSizeOption>(FACTORY_DEFAULTS.paper_size);
  const [pageFlip, setPageFlip] = useState<PageFlipMode>(FACTORY_DEFAULTS.page_flip);
  const [collate, setCollate] = useState<boolean>(FACTORY_DEFAULTS.collate);
  const [contentType, setContentType] = useState<ContentTypeMode>(FACTORY_DEFAULTS.content_type);

  // Modals & status
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [copiesKeypadOpen, setCopiesKeypadOpen] = useState(false);
  const [keypadBuffer, setKeypadBuffer] = useState("");
  const [savingDefaults, setSavingDefaults] = useState(false);
  const [savedBanner, setSavedBanner] = useState<string | null>(null);

  const [stage, setStage] = useState<Stage>("idle");
  const [errorDetail, setErrorDetail] = useState<string | null>(null);
  const [pendingScanId, setPendingScanId] = useState<string | null>(null);
  const [scannedPages, setScannedPages] = useState<number>(0);
  const [previewPage, setPreviewPage] = useState<number>(0);
  const [previewRev, setPreviewRev] = useState<number>(0);
  const [rotatingPreview, setRotatingPreview] = useState<boolean>(false);
  const [copiedError, setCopiedError] = useState(false);
  const [cancelling, setCancelling] = useState(false);
  const busyLock = useRef(false);
  const cancelledRef = useRef(false);

  const hardwareBusy = stage === "scanning" || stage === "printing";
  const currentSided = SIDED_META[sidedMode];
  const currentQuality = QUALITY_META[quality];
  const isMultiPageFlatbed =
    source === "flatbed" && (sidedMode !== "1_to_1" || resizeMode === "two_on_one");

  function applyDefaultsPayload(d: Partial<CopyDefaultsPayload>) {
    if (d.sided_mode && SIDED_CYCLE.includes(d.sided_mode)) setSidedMode(d.sided_mode);
    if (typeof d.color === "boolean") setColor(d.color);
    if (d.source === "flatbed" || d.source === "adf") setSource(d.source);
    if (d.quality && QUALITY_CYCLE.includes(d.quality)) setQuality(d.quality);
    if (typeof d.lighter_darker === "number") {
      setLighterDarker(Math.max(-4, Math.min(4, Math.round(d.lighter_darker))));
    }
    if (d.resize_mode && d.resize_mode in RESIZE_LABELS) setResizeMode(d.resize_mode);
    if (typeof d.resize_percent === "number") {
      setResizePercent(Math.max(25, Math.min(400, Math.round(d.resize_percent))));
    }
    if (d.original_size && PAPER_SIZES.includes(d.original_size)) setOriginalSize(d.original_size);
    if (d.paper_size && PAPER_SIZES.includes(d.paper_size)) setPaperSize(d.paper_size);
    if (d.page_flip === "long_edge" || d.page_flip === "short_edge") setPageFlip(d.page_flip);
    if (typeof d.collate === "boolean") setCollate(d.collate);
    if (d.content_type === "mixed" || d.content_type === "text" || d.content_type === "photo") {
      setContentType(d.content_type);
    }
  }

  useEffect(() => {
    let active = true;
    fetch(apiUrl("/api/copy/defaults"))
      .then((r) => (r.ok ? r.json() : null))
      .then((data: Partial<CopyDefaultsPayload> | null) => {
        if (active && data) {
          applyDefaultsPayload(data);
          if (copyMode === "photo") {
            setContentType("photo");
            setQuality("best");
            setColor(true);
            setSource("flatbed");
          }
        }
      })
      .catch(() => {
        /* fallback to factory defaults */
      });
    return () => {
      active = false;
    };
  }, [copyMode]);

  useEffect(() => {
    if (copyMode === "photo") {
      setContentType("photo");
      setQuality("best");
      setColor(true);
      setSource("flatbed");
    } else if (copyMode === "document") {
      setContentType("mixed");
    }
  }, [copyMode]);

  useEffect(() => {
    if (stage !== "done") return;
    const t = window.setTimeout(() => {
      setStage("idle");
      busyLock.current = false;
    }, 2000);
    return () => window.clearTimeout(t);
  }, [stage]);

  function adjustCopies(delta: number) {
    setCopies((prev) => Math.max(1, Math.min(99, prev + delta)));
  }

  function cycleSidedMode() {
    setSidedMode((prev) => {
      const idx = SIDED_CYCLE.indexOf(prev);
      return SIDED_CYCLE[(idx + 1) % SIDED_CYCLE.length];
    });
  }

  function cycleQuality() {
    setQuality((prev) => {
      const idx = QUALITY_CYCLE.indexOf(prev);
      return QUALITY_CYCLE[(idx + 1) % QUALITY_CYCLE.length];
    });
  }

  function selectQuickPreset(preset: "document" | "photo") {
    if (preset === "photo") {
      setContentType("photo");
      setQuality("best");
      setColor(true);
      nav("/copy/photo", { replace: true });
    } else {
      setContentType("mixed");
      setQuality("normal");
      nav("/copy/document", { replace: true });
    }
  }

  async function saveCurrentAsDefaults(payloadOverride?: CopyDefaultsPayload, bannerText?: string) {
    setSavingDefaults(true);
    setSavedBanner(null);
    const payload: CopyDefaultsPayload = payloadOverride ?? {
      sided_mode: sidedMode,
      color,
      source,
      quality,
      lighter_darker: lighterDarker,
      resize_mode: resizeMode,
      resize_percent: resizePercent,
      original_size: originalSize,
      paper_size: paperSize,
      page_flip: pageFlip,
      collate,
      content_type: contentType,
    };
    try {
      const res = await fetch(apiUrl("/api/copy/defaults"), {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (res.ok) {
        setSavedBanner(bannerText ?? "Saved as Default!");
        window.setTimeout(() => setSavedBanner(null), 2500);
      }
    } catch {
      /* ignore */
    } finally {
      setSavingDefaults(false);
    }
  }

  async function resetToFactoryDefaults() {
    applyDefaultsPayload(FACTORY_DEFAULTS);
    await saveCurrentAsDefaults(FACTORY_DEFAULTS, "Factory Defaults Restored");
  }

  async function cancelOperation() {
    if (cancelling) return;
    setCancelling(true);
    cancelledRef.current = true;
    const discardQuery = pendingScanId ? `?scan_id=${encodeURIComponent(pendingScanId)}` : "";
    try {
      await fetch(apiUrl(`/api/copy/cancel${discardQuery}`), { method: "POST" });
    } catch {
      /* ignore network errors during cancel */
    } finally {
      setCancelling(false);
      setPendingScanId(null);
      setScannedPages(0);
      setPreviewPage(0);
      setErrorDetail(null);
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

  async function copyErrorToClipboard() {
    if (!errorDetail) return;
    try {
      await navigator.clipboard.writeText(errorDetail);
      setCopiedError(true);
      window.setTimeout(() => setCopiedError(false), 2000);
    } catch {
      /* user can still select text manually */
    }
  }

  async function runPrintStep(scanId: string) {
    if (cancelledRef.current) return;
    busyLock.current = true;
    setStage("printing");
    try {
      const printRes = await fetch(apiUrl("/api/print"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          scan_id: scanId,
          copies,
          duplex: currentSided.printDuplex,
          page_flip: pageFlip,
          color,
          paper_size: paperSize,
          collate,
          resize_mode: resizeMode,
          quality,
        }),
      });
      if (cancelledRef.current) return;
      if (!printRes.ok) {
        const msg = await parseErrorDetail(printRes);
        setErrorDetail(msg);
        setStage("error");
        busyLock.current = false;
        return;
      }
      setPendingScanId(null);
      setScannedPages(0);
      setPreviewPage(0);
      setStage("done");
      busyLock.current = false;
    } catch (e) {
      if (cancelledRef.current) return;
      setErrorDetail(e instanceof Error ? e.message : "Network error");
      setStage("error");
      busyLock.current = false;
    }
  }

  async function runScanStep(appendToScanId?: string | null, forcePreview?: boolean) {
    if (busyLock.current) return;
    busyLock.current = true;
    cancelledRef.current = false;
    setErrorDetail(null);
    setStage("scanning");

    const effectiveSource =
      source === "flatbed"
        ? "flatbed"
        : currentSided.scanDuplex
          ? "adf_duplex"
          : "adf";
    const effectiveScanDuplex = source === "flatbed" ? false : currentSided.scanDuplex;

    let scanId: string;
    let totalPages = 1;
    try {
      const scanRes = await fetch(apiUrl("/api/scan"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          duplex: effectiveScanDuplex,
          color,
          resolution_dpi: currentQuality.dpi,
          source: effectiveSource,
          original_size: originalSize,
          lighter_darker: lighterDarker,
          content_type: contentType,
          resize_mode: resizeMode,
          resize_percent: resizePercent,
          append_to_scan_id: appendToScanId ?? null,
        }),
      });
      if (cancelledRef.current) return;
      if (!scanRes.ok) {
        const msg = await parseErrorDetail(scanRes);
        setErrorDetail(msg);
        setStage("error");
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
      setErrorDetail(e instanceof Error ? e.message : "Network error");
      setStage("error");
      busyLock.current = false;
      return;
    }

    if (isMultiPageFlatbed || forcePreview) {
      setStage("awaiting_next_page");
      busyLock.current = false;
      return;
    }

    await runPrintStep(scanId);
  }

  async function startCopy() {
    if (busyLock.current) return;
    if (pendingScanId && stage !== "awaiting_next_page") {
      await runPrintStep(pendingScanId);
      return;
    }
    await runScanStep(null, false);
  }

  async function startPreview() {
    if (busyLock.current) return;
    await runScanStep(null, true);
  }

  function resetFromError(clearCachedScan: boolean) {
    if (clearCachedScan) {
      setPendingScanId(null);
      setScannedPages(0);
      setPreviewPage(0);
    }
    setErrorDetail(null);
    setStage("idle");
    busyLock.current = false;
  }

  const effectiveSourceLabel =
    source === "flatbed"
      ? "Flatbed"
      : currentSided.scanDuplex
        ? "ADF Duplex"
        : "ADF";

  const resizeSummary =
    resizeMode === "actual"
      ? "100%"
      : resizeMode === "full_page_91"
        ? "91%"
        : resizeMode === "fit_to_page"
          ? "Fit"
          : resizeMode === "two_on_one"
            ? "2-on-1"
            : `${resizePercent}%`;

  const densitySummary =
    lighterDarker === 0
      ? "Normal"
      : lighterDarker < 0
        ? `Lighter ${lighterDarker}`
        : `Darker +${lighterDarker}`;

  const hasCustomAdvanced =
    lighterDarker !== 0 ||
    resizeMode !== "actual" ||
    paperSize !== "A4" ||
    originalSize !== "A4" ||
    contentType !== "mixed" ||
    pageFlip !== "long_edge" ||
    !collate;

  // ============================================================================
  // VIEW 1: HP 9010 Top-Level Copy Mode Selector (/copy)
  // ============================================================================
  if (!copyMode) {
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
                HP 9010 Copier
              </p>
              <h1 className="text-xl font-black uppercase tracking-wide text-zinc-100 md:text-2xl">
                Copy — Select Mode
              </h1>
            </div>
          </div>
        </header>

        <main className="mx-auto flex min-h-0 w-full max-w-5xl flex-1 flex-col justify-center gap-4 p-4 md:grid md:grid-cols-3 md:items-stretch md:gap-6 md:p-8">
          <KioskButton
            layout="tile"
            variant="industrial"
            className="min-h-[9rem] md:min-h-[16rem]"
            onClick={() => nav("/copy/document")}
          >
            <span className="text-3xl md:text-4xl">📄</span>
            <span className="mt-2 block text-xl font-black uppercase tracking-wide md:text-2xl">
              Document
            </span>
            <span className="mt-1.5 block text-xs font-medium normal-case tracking-normal text-zinc-400">
              Standard 1-sided or 2-sided document copying with preview & resize
            </span>
          </KioskButton>

          <KioskButton
            layout="tile"
            variant="industrial"
            className="min-h-[9rem] md:min-h-[16rem]"
            onClick={() => nav("/id-scan")}
          >
            <span className="text-3xl md:text-4xl">🪪</span>
            <span className="mt-2 block text-xl font-black uppercase tracking-wide md:text-2xl">
              ID Card
            </span>
            <span className="mt-1.5 block text-xs font-medium normal-case tracking-normal text-zinc-400">
              Guided 2-sided ID card capture arranged onto a single A4 page
            </span>
          </KioskButton>

          <KioskButton
            layout="tile"
            variant="industrial"
            className="min-h-[9rem] md:min-h-[16rem]"
            onClick={() => nav("/copy/photo")}
          >
            <span className="text-3xl md:text-4xl">🖼️</span>
            <span className="mt-2 block text-xl font-black uppercase tracking-wide md:text-2xl">
              Photo
            </span>
            <span className="mt-1.5 block text-xs font-medium normal-case tracking-normal text-zinc-400">
              High-detail 600 DPI full-color photo copy on the flatbed glass
            </span>
          </KioskButton>
        </main>
      </div>
    );
  }

  return (
    <div className="flex h-[100dvh] w-[100dvw] flex-col overflow-hidden bg-kiosk-industrial-bezel text-zinc-100">
      <header className="flex shrink-0 items-center justify-between gap-2 border-b border-kiosk-industrial-border bg-kiosk-industrial-navy px-3 py-2 md:px-6">
        <div className="flex items-center gap-3">
          <button
            type="button"
            disabled={hardwareBusy}
            onClick={() => nav("/copy")}
            className="flex h-11 items-center justify-center rounded-xl border border-kiosk-industrial-border bg-kiosk-industrial-slate px-3.5 text-sm font-black uppercase tracking-wider text-zinc-100 disabled:opacity-40 active:scale-95"
          >
            ← Back
          </button>
          <div>
            <p className="text-[10px] font-semibold uppercase tracking-wider text-zinc-500">
              HP 9010 Copier
            </p>
            <h1 className="text-lg font-black uppercase tracking-wide text-zinc-100 md:text-2xl">
              {copyMode === "photo" ? "Photo Copy" : "Document Copy"}
            </h1>
          </div>
        </div>

        {/* HP 9010 Top-Level Mode Selector (Document / Photo / ID Card) */}
        <div className="hidden items-center gap-1.5 rounded-xl border border-kiosk-industrial-border bg-kiosk-industrial-slate/60 p-1 sm:flex">
          <button
            type="button"
            disabled={hardwareBusy}
            onClick={() => selectQuickPreset("document")}
            className={`rounded-lg px-3 py-1.5 text-xs font-bold uppercase tracking-wider transition ${
              contentType !== "photo"
                ? "bg-amber-500/20 text-amber-300 ring-1 ring-amber-500/50"
                : "text-zinc-400 hover:text-zinc-200"
            }`}
          >
            Document
          </button>
          <button
            type="button"
            disabled={hardwareBusy}
            onClick={() => selectQuickPreset("photo")}
            className={`rounded-lg px-3 py-1.5 text-xs font-bold uppercase tracking-wider transition ${
              contentType === "photo"
                ? "bg-amber-500/20 text-amber-300 ring-1 ring-amber-500/50"
                : "text-zinc-400 hover:text-zinc-200"
            }`}
          >
            Photo
          </button>
          <button
            type="button"
            disabled={hardwareBusy}
            onClick={() => nav("/id-scan")}
            className="rounded-lg px-3 py-1.5 text-xs font-bold uppercase tracking-wider text-zinc-400 transition hover:text-zinc-200"
          >
            ID Card ↗
          </button>
        </div>

        {/* Preview Button + Copies Counter */}
        <div className="flex items-center gap-2">
          {stage === "idle" && (
            <button
              type="button"
              disabled={hardwareBusy}
              onClick={() => void startPreview()}
              className="flex h-11 items-center gap-1.5 rounded-xl border border-amber-500/40 bg-amber-500/15 px-3.5 text-xs font-black uppercase tracking-wider text-amber-300 disabled:opacity-40 active:scale-95"
              title="Scan and preview before printing"
            >
              🔍 Preview
            </button>
          )}
          <div className="flex items-center gap-1.5 rounded-xl border border-kiosk-industrial-border bg-kiosk-industrial-slate/70 px-2.5 py-1.5">
            <span className="mr-1 hidden text-xs font-semibold uppercase tracking-wider text-zinc-400 md:inline">
              Copies
            </span>
            <button
              type="button"
              disabled={hardwareBusy || copies <= 1}
              onClick={() => adjustCopies(-1)}
              className="flex h-9 w-9 items-center justify-center rounded-lg border border-kiosk-industrial-border bg-kiosk-industrial-navy text-xl font-bold text-zinc-100 disabled:opacity-40 active:scale-95"
              aria-label="Decrease copies"
            >
              −
            </button>
            <button
              type="button"
              disabled={hardwareBusy}
              onClick={() => {
                setKeypadBuffer(String(copies));
                setCopiesKeypadOpen(true);
              }}
              className="min-w-[2.75rem] rounded-lg px-1.5 py-0.5 text-center font-mono text-2xl font-black tabular-nums text-emerald-400 hover:bg-white/5 active:scale-95"
              title="Tap to enter copy count"
            >
              {copies}
            </button>
            <button
              type="button"
              disabled={hardwareBusy || copies >= 99}
              onClick={() => adjustCopies(1)}
              className="flex h-9 w-9 items-center justify-center rounded-lg border border-kiosk-industrial-border bg-kiosk-industrial-navy text-xl font-bold text-zinc-100 disabled:opacity-40 active:scale-95"
              aria-label="Increase copies"
            >
              +
            </button>
          </div>
        </div>
      </header>

      <main className="flex min-h-0 flex-1 items-center justify-center px-3 py-2 md:px-6">
        {(stage === "scanning" || stage === "printing") && (
          <div className="flex w-full max-w-xl flex-col items-center gap-6 px-2">
            <div className="w-full">
              {stage === "scanning" ? (
                <ProgressBar
                  label={
                    isMultiPageFlatbed
                      ? `Scanning Page ${scannedPages + 1} from Flatbed…`
                      : "Scanning…"
                  }
                  variant="scan"
                />
              ) : (
                <ProgressBar
                  label={`Printing ${copies} ${copies === 1 ? "copy" : "copies"}…`}
                  variant="print"
                />
              )}
            </div>
            <KioskButton
              variant="industrial"
              className="min-h-[4rem] w-full max-w-xs border-2 border-red-500/70 bg-red-950/60 text-xl font-black uppercase tracking-wider text-red-200 ring-2 ring-red-500/30"
              disabled={cancelling}
              onClick={cancelOperation}
            >
              {cancelling ? "Stopping…" : "Stop / Cancel"}
            </KioskButton>
          </div>
        )}

        {stage === "awaiting_next_page" && pendingScanId && (
          <div className="flex max-h-full w-full max-w-4xl flex-col gap-4 rounded-3xl border-2 border-amber-500/50 bg-kiosk-industrial-slate/95 p-4 shadow-2xl md:flex-row md:items-stretch md:p-6">
            {/* Left / Top: Live Scanned Page Preview */}
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

              <div className="flex max-h-[42dvh] min-h-[12rem] w-full flex-1 items-center justify-center overflow-hidden rounded-xl bg-zinc-900/80 p-2 md:max-h-[54dvh]">
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

            {/* Right / Bottom: Actions & Multi-Page Controls */}
            <div className="flex flex-col justify-between gap-3 md:w-72">
              <div>
                <p className="text-xs font-bold uppercase tracking-widest text-amber-400">
                  Copy Preview ({currentSided.title})
                </p>
                <h2 className="mt-1 text-2xl font-black text-zinc-100">
                  {scannedPages} {scannedPages === 1 ? "Page" : "Pages"} Ready
                </h2>
                <p className="mt-2 text-sm leading-snug text-zinc-300">
                  {source === "flatbed"
                    ? currentSided.scanDuplex
                      ? "Flip the document over (or place the next page) on the glass to add another page, or tap Finish & Print."
                      : "Place the next page on the scanner glass to add it to this copy job, or tap Finish & Print."
                    : "Review the scanned document pages before sending to the printer."}
                </p>
              </div>

              <div className="flex flex-col gap-2.5">
                {source === "flatbed" && (
                  <KioskButton
                    variant="industrial"
                    className="min-h-[3.75rem] w-full text-base ring-1 ring-amber-500/40"
                    onClick={() => void runScanStep(pendingScanId, true)}
                  >
                    + Scan Page {scannedPages + 1}
                  </KioskButton>
                )}
                <KioskButton
                  variant="primary"
                  className="min-h-[4rem] w-full text-lg"
                  onClick={() => void runPrintStep(pendingScanId)}
                >
                  Finish & Print ({copies})
                </KioskButton>
                <button
                  type="button"
                  onClick={() => void cancelOperation()}
                  className="mt-1 rounded-xl border border-red-500/40 bg-red-950/40 py-2.5 text-sm font-bold uppercase tracking-wider text-red-300 active:scale-95"
                >
                  Cancel Job
                </button>
              </div>
            </div>
          </div>
        )}

        {stage === "done" && (
          <div className="flex max-w-xl flex-col items-center rounded-3xl border-2 border-emerald-500/40 bg-kiosk-industrial-slate/80 p-8 text-center shadow-xl">
            <p className="text-3xl font-black text-zinc-100 md:text-4xl">Done</p>
            <p className="mt-3 text-lg text-zinc-400">
              Submitted {copies} {copies === 1 ? "copy" : "copies"} to printer.
            </p>
          </div>
        )}

        {stage === "error" && errorDetail && (
          <div className="max-h-[min(70dvh,28rem)] w-full max-w-xl overflow-auto rounded-3xl border-2 border-red-500/50 bg-kiosk-industrial-slate/90 p-6 shadow-xl">
            <p className="text-2xl font-black text-zinc-100 select-text">Check hardware</p>
            <p className="mt-3 whitespace-pre-wrap rounded-xl bg-black/30 p-3 font-mono text-sm leading-snug text-zinc-300 select-text cursor-text">
              {errorDetail}
            </p>
            <div className="mt-6 flex flex-wrap justify-center gap-3">
              <KioskButton
                variant="industrialMuted"
                className="min-h-[3.5rem] flex-1 text-base"
                onClick={copyErrorToClipboard}
              >
                {copiedError ? "Copied!" : "Copy Error"}
              </KioskButton>
              {pendingScanId && (
                <KioskButton
                  variant="primary"
                  className="min-h-[3.5rem] flex-1 text-lg"
                  onClick={() => {
                    setErrorDetail(null);
                    void runPrintStep(pendingScanId);
                  }}
                >
                  Retry Print
                </KioskButton>
              )}
              <KioskButton
                variant="industrial"
                className="min-h-[3.5rem] flex-1 text-lg"
                onClick={() => resetFromError(true)}
              >
                Back to Options
              </KioskButton>
            </div>
          </div>
        )}

        {stage === "idle" && (
          <div
            className="grid min-h-0 grid-cols-3 grid-rows-2 gap-3 md:gap-4"
            style={GRID_STYLE}
          >
            {/* 1. Unified Sides button: cycles 1->1, 1->2, 2->2, 2->1 */}
            <KioskButton
              layout="tile"
              variant="industrial"
              tileActive={sidedMode !== "1_to_1"}
              className="min-h-0 min-w-0"
              disabled={hardwareBusy}
              onClick={cycleSidedMode}
            >
              <span>{currentSided.title}</span>
              <span className="mt-1 block text-[11px] font-medium normal-case tracking-normal text-zinc-400">
                {currentSided.subtitle}
              </span>
            </KioskButton>

            {/* 2. Unified Color / B&W toggle button */}
            <KioskButton
              layout="tile"
              variant="industrial"
              tileActive={color}
              className="min-h-0 min-w-0"
              disabled={hardwareBusy}
              onClick={() => setColor((c) => !c)}
            >
              <span>{color ? "Color" : "B&W"}</span>
              <span className="mt-1 block text-[11px] font-medium normal-case tracking-normal text-zinc-400">
                {color ? "Full Color" : "Grayscale"}
              </span>
            </KioskButton>

            {/* 3. Paper Source toggle button (unlocked for all Sides modes!) */}
            <KioskButton
              layout="tile"
              variant="industrial"
              tileActive={source === "adf"}
              className="min-h-0 min-w-0"
              disabled={hardwareBusy}
              onClick={() => setSource((s) => (s === "flatbed" ? "adf" : "flatbed"))}
            >
              <span>{effectiveSourceLabel}</span>
              <span className="mt-1 block text-[11px] font-medium normal-case tracking-normal text-zinc-400">
                {isMultiPageFlatbed ? "Step-by-Step Glass Scan" : "Source (Tap to Switch)"}
              </span>
            </KioskButton>

            {/* 4. Quality cycle button (Draft / Normal / Best) */}
            <KioskButton
              layout="tile"
              variant="industrial"
              tileActive={quality !== "normal"}
              className="min-h-0 min-w-0"
              disabled={hardwareBusy}
              onClick={cycleQuality}
            >
              <span>{currentQuality.label}</span>
              <span className="mt-1 block text-[11px] font-medium normal-case tracking-normal text-zinc-400">
                {currentQuality.subtitle}
              </span>
            </KioskButton>

            {/* 5. HP 9010 Copy Settings (⚙️ More Options) */}
            <KioskButton
              layout="tile"
              variant="industrial"
              tileActive={hasCustomAdvanced}
              className="min-h-0 min-w-0"
              disabled={hardwareBusy}
              onClick={() => setSettingsOpen(true)}
            >
              <span>⚙️ Settings</span>
              <span className="mt-1 block text-[11px] font-medium normal-case tracking-normal text-zinc-400">
                {resizeSummary} • {densitySummary} • {paperSize}
              </span>
            </KioskButton>

            {/* 6. Start Copy */}
            <KioskButton
              layout="tile"
              variant="industrial"
              className="min-h-0 min-w-0 ring-1 ring-amber-500/30"
              disabled={hardwareBusy}
              onClick={startCopy}
            >
              Start ({copies})
            </KioskButton>
          </div>
        )}
      </main>

      {/* Direct Copies Keypad Modal */}
      {copiesKeypadOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 p-4">
          <div className="w-full max-w-sm rounded-3xl border border-kiosk-industrial-border bg-kiosk-industrial-navy p-5 shadow-2xl">
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-black uppercase tracking-wider text-zinc-100">
                Number of Copies (1–99)
              </h2>
              <button
                type="button"
                onClick={() => setCopiesKeypadOpen(false)}
                className="rounded-lg px-3 py-1 text-sm font-bold text-zinc-400 hover:text-zinc-100"
              >
                ✕
              </button>
            </div>
            <div className="my-3 rounded-xl border border-kiosk-industrial-border bg-black/40 py-2.5 text-center font-mono text-3xl font-black text-emerald-400">
              {keypadBuffer || "1"}
            </div>
            <div className="grid grid-cols-3 gap-2">
              {["1", "2", "3", "4", "5", "6", "7", "8", "9", "C", "0", "⌫"].map((key) => (
                <button
                  key={key}
                  type="button"
                  onClick={() => {
                    if (key === "C") {
                      setKeypadBuffer("");
                    } else if (key === "⌫") {
                      setKeypadBuffer((b) => b.slice(0, -1));
                    } else {
                      setKeypadBuffer((b) => {
                        const next = (b + key).replace(/^0+/, "");
                        return next.length <= 2 ? next : b;
                      });
                    }
                  }}
                  className="flex h-12 items-center justify-center rounded-xl border border-kiosk-industrial-border bg-kiosk-industrial-slate text-xl font-bold text-zinc-100 active:scale-95"
                >
                  {key}
                </button>
              ))}
            </div>
            <div className="mt-4 flex gap-2">
              <KioskButton
                variant="industrialMuted"
                className="min-h-[3.25rem] flex-1 text-base"
                onClick={() => setCopiesKeypadOpen(false)}
              >
                Cancel
              </KioskButton>
              <KioskButton
                variant="industrial"
                className="min-h-[3.25rem] flex-1 text-base ring-1 ring-emerald-500/40"
                onClick={() => {
                  const parsed = parseInt(keypadBuffer, 10);
                  if (!Number.isNaN(parsed) && parsed >= 1) {
                    setCopies(Math.min(99, parsed));
                  }
                  setCopiesKeypadOpen(false);
                }}
              >
                OK
              </KioskButton>
            </div>
          </div>
        </div>
      )}

      {/* HP OfficeJet Pro 9010 Copy Settings Drawer / Modal */}
      {settingsOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-3 md:p-6">
          <div className="flex max-h-[92dvh] w-full max-w-3xl flex-col overflow-hidden rounded-3xl border border-kiosk-industrial-border bg-kiosk-industrial-navy shadow-2xl">
            <div className="flex shrink-0 items-center justify-between border-b border-kiosk-industrial-border px-5 py-3.5">
              <div>
                <p className="text-[10px] font-semibold uppercase tracking-wider text-zinc-400">
                  HP OfficeJet Pro 9010
                </p>
                <h2 className="text-xl font-black uppercase tracking-wide text-zinc-100">
                  Copy Settings
                </h2>
              </div>
              <button
                type="button"
                onClick={() => setSettingsOpen(false)}
                className="rounded-xl border border-kiosk-industrial-border bg-kiosk-industrial-slate px-4 py-2 text-sm font-black uppercase tracking-wider text-zinc-100 active:scale-95"
              >
                Done ✓
              </button>
            </div>

            <div className="flex-1 space-y-5 overflow-y-auto p-5">
              {/* 2.1 Lighter / Darker */}
              <section className="rounded-2xl border border-kiosk-industrial-border bg-kiosk-industrial-slate/60 p-4">
                <div className="flex items-center justify-between">
                  <span className="text-sm font-black uppercase tracking-wider text-zinc-200">
                    Lighter / Darker
                  </span>
                  <span className="font-mono text-sm font-bold text-amber-400">
                    {densitySummary}
                  </span>
                </div>
                <div className="mt-3 flex items-center gap-3">
                  <button
                    type="button"
                    disabled={lighterDarker <= -4}
                    onClick={() => setLighterDarker((v) => Math.max(-4, v - 1))}
                    className="flex h-11 w-14 items-center justify-center rounded-xl border border-kiosk-industrial-border bg-kiosk-industrial-navy text-sm font-bold text-zinc-100 disabled:opacity-40 active:scale-95"
                  >
                    Lighter
                  </button>
                  <div className="grid flex-1 grid-cols-9 gap-1.5">
                    {[-4, -3, -2, -1, 0, 1, 2, 3, 4].map((step) => (
                      <button
                        key={step}
                        type="button"
                        onClick={() => setLighterDarker(step)}
                        className={`flex h-10 items-center justify-center rounded-lg border text-xs font-bold transition ${
                          lighterDarker === step
                            ? "border-amber-400 bg-amber-500/30 text-amber-200"
                            : "border-kiosk-industrial-border bg-black/30 text-zinc-400"
                        }`}
                      >
                        {step > 0 ? `+${step}` : step}
                      </button>
                    ))}
                  </div>
                  <button
                    type="button"
                    disabled={lighterDarker >= 4}
                    onClick={() => setLighterDarker((v) => Math.min(4, v + 1))}
                    className="flex h-11 w-14 items-center justify-center rounded-xl border border-kiosk-industrial-border bg-kiosk-industrial-navy text-sm font-bold text-zinc-100 disabled:opacity-40 active:scale-95"
                  >
                    Darker
                  </button>
                </div>
              </section>

              {/* 2.2 Resize (Reduce / Enlarge) */}
              <section className="rounded-2xl border border-kiosk-industrial-border bg-kiosk-industrial-slate/60 p-4">
                <div className="flex items-center justify-between">
                  <span className="text-sm font-black uppercase tracking-wider text-zinc-200">
                    Resize
                  </span>
                  <span className="font-mono text-sm font-bold text-amber-400">
                    {RESIZE_LABELS[resizeMode]}
                    {resizeMode === "custom" ? ` (${resizePercent}%)` : ""}
                  </span>
                </div>
                <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-3">
                  {(Object.keys(RESIZE_LABELS) as ResizeMode[]).map((mode) => (
                    <button
                      key={mode}
                      type="button"
                      onClick={() => setResizeMode(mode)}
                      className={`rounded-xl border px-3 py-2.5 text-xs font-bold uppercase tracking-wider transition ${
                        resizeMode === mode
                          ? "border-amber-400 bg-amber-500/25 text-amber-200"
                          : "border-kiosk-industrial-border bg-kiosk-industrial-navy text-zinc-300"
                      }`}
                    >
                      {RESIZE_LABELS[mode]}
                    </button>
                  ))}
                </div>
                {resizeMode === "custom" && (
                  <div className="mt-3 flex items-center justify-center gap-2 rounded-xl bg-black/30 p-2.5">
                    {[-25, -5, -1].map((delta) => (
                      <button
                        key={delta}
                        type="button"
                        onClick={() =>
                          setResizePercent((p) => Math.max(25, Math.min(400, p + delta)))
                        }
                        className="rounded-lg border border-kiosk-industrial-border bg-kiosk-industrial-navy px-3 py-1.5 text-xs font-bold text-zinc-200 active:scale-95"
                      >
                        {delta}%
                      </button>
                    ))}
                    <span className="min-w-[4.5rem] text-center font-mono text-lg font-black text-emerald-400">
                      {resizePercent}%
                    </span>
                    {[1, 5, 25].map((delta) => (
                      <button
                        key={delta}
                        type="button"
                        onClick={() =>
                          setResizePercent((p) => Math.max(25, Math.min(400, p + delta)))
                        }
                        className="rounded-lg border border-kiosk-industrial-border bg-kiosk-industrial-navy px-3 py-1.5 text-xs font-bold text-zinc-200 active:scale-95"
                      >
                        +{delta}%
                      </button>
                    ))}
                  </div>
                )}
              </section>

              {/* 2.3 Original Size & Tray / Paper Size */}
              <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                <section className="rounded-2xl border border-kiosk-industrial-border bg-kiosk-industrial-slate/60 p-4">
                  <span className="text-sm font-black uppercase tracking-wider text-zinc-200">
                    Original Size
                  </span>
                  <div className="mt-2.5 flex flex-wrap gap-1.5">
                    {PAPER_SIZES.map((sz) => (
                      <button
                        key={sz}
                        type="button"
                        onClick={() => setOriginalSize(sz)}
                        className={`rounded-xl border px-3 py-2 text-xs font-bold transition ${
                          originalSize === sz
                            ? "border-amber-400 bg-amber-500/25 text-amber-200"
                            : "border-kiosk-industrial-border bg-kiosk-industrial-navy text-zinc-300"
                        }`}
                      >
                        {sz}
                      </button>
                    ))}
                  </div>
                </section>

                <section className="rounded-2xl border border-kiosk-industrial-border bg-kiosk-industrial-slate/60 p-4">
                  <span className="text-sm font-black uppercase tracking-wider text-zinc-200">
                    Tray / Paper Size
                  </span>
                  <div className="mt-2.5 flex flex-wrap gap-1.5">
                    {PAPER_SIZES.map((sz) => (
                      <button
                        key={sz}
                        type="button"
                        onClick={() => setPaperSize(sz)}
                        className={`rounded-xl border px-3 py-2 text-xs font-bold transition ${
                          paperSize === sz
                            ? "border-amber-400 bg-amber-500/25 text-amber-200"
                            : "border-kiosk-industrial-border bg-kiosk-industrial-navy text-zinc-300"
                        }`}
                      >
                        {sz}
                      </button>
                    ))}
                  </div>
                </section>
              </div>

              {/* 2.4 Two-Sided Page Flip, 2.5 Collate, 2.6 Content Enhancement */}
              <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
                <section className="rounded-2xl border border-kiosk-industrial-border bg-kiosk-industrial-slate/60 p-4">
                  <span className="text-xs font-black uppercase tracking-wider text-zinc-200">
                    Two-Sided Page Flip
                  </span>
                  <div className="mt-2.5 flex flex-col gap-1.5">
                    <button
                      type="button"
                      onClick={() => setPageFlip("long_edge")}
                      className={`rounded-xl border px-3 py-2 text-left text-xs font-bold transition ${
                        pageFlip === "long_edge"
                          ? "border-amber-400 bg-amber-500/25 text-amber-200"
                          : "border-kiosk-industrial-border bg-kiosk-industrial-navy text-zinc-300"
                      }`}
                    >
                      Book (Long Edge)
                    </button>
                    <button
                      type="button"
                      onClick={() => setPageFlip("short_edge")}
                      className={`rounded-xl border px-3 py-2 text-left text-xs font-bold transition ${
                        pageFlip === "short_edge"
                          ? "border-amber-400 bg-amber-500/25 text-amber-200"
                          : "border-kiosk-industrial-border bg-kiosk-industrial-navy text-zinc-300"
                      }`}
                    >
                      Tablet (Short Edge)
                    </button>
                  </div>
                </section>

                <section className="rounded-2xl border border-kiosk-industrial-border bg-kiosk-industrial-slate/60 p-4">
                  <span className="text-xs font-black uppercase tracking-wider text-zinc-200">
                    Collate Copies
                  </span>
                  <div className="mt-2.5 flex flex-col gap-1.5">
                    <button
                      type="button"
                      onClick={() => setCollate(true)}
                      className={`rounded-xl border px-3 py-2 text-left text-xs font-bold transition ${
                        collate
                          ? "border-amber-400 bg-amber-500/25 text-amber-200"
                          : "border-kiosk-industrial-border bg-kiosk-industrial-navy text-zinc-300"
                      }`}
                    >
                      On (1-2-3, 1-2-3)
                    </button>
                    <button
                      type="button"
                      onClick={() => setCollate(false)}
                      className={`rounded-xl border px-3 py-2 text-left text-xs font-bold transition ${
                        !collate
                          ? "border-amber-400 bg-amber-500/25 text-amber-200"
                          : "border-kiosk-industrial-border bg-kiosk-industrial-navy text-zinc-300"
                      }`}
                    >
                      Off (1-1, 2-2, 3-3)
                    </button>
                  </div>
                </section>

                <section className="rounded-2xl border border-kiosk-industrial-border bg-kiosk-industrial-slate/60 p-4">
                  <span className="text-xs font-black uppercase tracking-wider text-zinc-200">
                    Content Type
                  </span>
                  <div className="mt-2.5 flex flex-col gap-1.5">
                    {(["mixed", "text", "photo"] as ContentTypeMode[]).map((ct) => (
                      <button
                        key={ct}
                        type="button"
                        onClick={() => setContentType(ct)}
                        className={`rounded-xl border px-3 py-1.5 text-left text-xs font-bold uppercase transition ${
                          contentType === ct
                            ? "border-amber-400 bg-amber-500/25 text-amber-200"
                            : "border-kiosk-industrial-border bg-kiosk-industrial-navy text-zinc-300"
                        }`}
                      >
                        {ct}
                      </button>
                    ))}
                  </div>
                </section>
              </div>
            </div>

            {/* 2.7 Save Current Settings as Default / Reset */}
            <div className="flex shrink-0 flex-wrap items-center justify-between gap-3 border-t border-kiosk-industrial-border bg-kiosk-industrial-slate/40 px-5 py-3">
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  disabled={savingDefaults}
                  onClick={() => void saveCurrentAsDefaults()}
                  className="rounded-xl border border-amber-500/50 bg-amber-500/20 px-4 py-2 text-xs font-black uppercase tracking-wider text-amber-200 active:scale-95 disabled:opacity-40"
                >
                  {savingDefaults ? "Saving…" : "Save as Default"}
                </button>
                <button
                  type="button"
                  disabled={savingDefaults}
                  onClick={() => void resetToFactoryDefaults()}
                  className="rounded-xl border border-kiosk-industrial-border bg-kiosk-industrial-navy px-4 py-2 text-xs font-bold uppercase tracking-wider text-zinc-300 active:scale-95 disabled:opacity-40"
                >
                  Reset Factory Defaults
                </button>
                {savedBanner && (
                  <span className="text-xs font-bold text-emerald-400">{savedBanner}</span>
                )}
              </div>
              <button
                type="button"
                onClick={() => setSettingsOpen(false)}
                className="rounded-xl bg-emerald-600 px-5 py-2 text-xs font-black uppercase tracking-wider text-white active:scale-95"
              >
                Apply & Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
