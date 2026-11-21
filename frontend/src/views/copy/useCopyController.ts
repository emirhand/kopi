import { useEffect, useRef, useState } from "react";
import { apiUrl, parseErrorDetail } from "../../api";
import {
  FACTORY_DEFAULTS,
  PAPER_SIZES,
  QUALITY_CYCLE,
  QUALITY_META,
  RESIZE_LABELS,
  SIDED_CYCLE,
  SIDED_META,
  type ContentTypeMode,
  type CopyDefaultsPayload,
  type PageFlipMode,
  type PaperSizeOption,
  type QualityMode,
  type ResizeMode,
  type SidedMode,
  type Stage,
} from "./copyTypes";

export function useCopyController(copyMode: "document" | "photo" | null) {
  const [copies, setCopies] = useState(1);
  const [sidedMode, setSidedMode] = useState<SidedMode>(FACTORY_DEFAULTS.sided_mode);
  const [color, setColor] = useState(FACTORY_DEFAULTS.color);
  const [source, setSource] = useState<"flatbed" | "adf">(FACTORY_DEFAULTS.source);
  const [quality, setQuality] = useState<QualityMode>(FACTORY_DEFAULTS.quality);

  const [lighterDarker, setLighterDarker] = useState<number>(FACTORY_DEFAULTS.lighter_darker);
  const [resizeMode, setResizeMode] = useState<ResizeMode>(FACTORY_DEFAULTS.resize_mode);
  const [resizePercent, setResizePercent] = useState<number>(FACTORY_DEFAULTS.resize_percent);
  const [originalSize, setOriginalSize] = useState<PaperSizeOption>(FACTORY_DEFAULTS.original_size);
  const [paperSize, setPaperSize] = useState<PaperSizeOption>(FACTORY_DEFAULTS.paper_size);
  const [pageFlip, setPageFlip] = useState<PageFlipMode>(FACTORY_DEFAULTS.page_flip);
  const [collate, setCollate] = useState<boolean>(FACTORY_DEFAULTS.collate);
  const [contentType, setContentType] = useState<ContentTypeMode>(FACTORY_DEFAULTS.content_type);

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

  return {
    copies,
    setCopies,
    sidedMode,
    color,
    setColor,
    source,
    setSource,
    quality,
    setQuality,
    lighterDarker,
    setLighterDarker,
    resizeMode,
    setResizeMode,
    resizePercent,
    setResizePercent,
    originalSize,
    setOriginalSize,
    paperSize,
    setPaperSize,
    pageFlip,
    setPageFlip,
    collate,
    setCollate,
    contentType,
    setContentType,
    settingsOpen,
    setSettingsOpen,
    copiesKeypadOpen,
    setCopiesKeypadOpen,
    keypadBuffer,
    setKeypadBuffer,
    savingDefaults,
    savedBanner,
    stage,
    errorDetail,
    setErrorDetail,
    pendingScanId,
    scannedPages,
    previewPage,
    setPreviewPage,
    previewRev,
    rotatingPreview,
    copiedError,
    cancelling,
    hardwareBusy,
    currentSided,
    currentQuality,
    isMultiPageFlatbed,
    effectiveSourceLabel,
    resizeSummary,
    densitySummary,
    hasCustomAdvanced,
    adjustCopies,
    cycleSidedMode,
    cycleQuality,
    saveCurrentAsDefaults,
    resetToFactoryDefaults,
    cancelOperation,
    rotateCurrentPreviewPage,
    copyErrorToClipboard,
    runPrintStep,
    runScanStep,
    startCopy,
    startPreview,
    resetFromError,
  };
}
