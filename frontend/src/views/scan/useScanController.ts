import { useRef, useState } from "react";
import { apiUrl, parseErrorDetail } from "../../api";
import { useUsbDrives } from "../../hooks/useUsbDrives";
import {
  FORMAT_CYCLE,
  QUALITY_CYCLE,
  QUALITY_META,
  type ScanDestination,
  type ScanFormat,
  type ScanQuality,
  type Stage,
} from "./scanTypes";

export function useScanController(destination: ScanDestination | null) {
  const [source, setSource] = useState<"flatbed" | "adf">("flatbed");
  const [scanDuplex, setScanDuplex] = useState(false);
  const [color, setColor] = useState(true);
  const [outputFormat, setOutputFormat] = useState<ScanFormat>("pdf");
  const [quality, setQuality] = useState<ScanQuality>("high");
  const [removeBlankPages, setRemoveBlankPages] = useState(false);

  const [email, setEmail] = useState("");
  const [emailSubject, setEmailSubject] = useState("");
  const [emailBody, setEmailBody] = useState("");
  const [fileName, setFileName] = useState("");

  const {
    usbDrives,
    selectedDevice: selectedUsbDevice,
    setSelectedDevice: setSelectedUsbDevice,
    loadingDrives,
    fetchDrives: fetchUsbDrives,
  } = useUsbDrives(destination === "usb");

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

  function cycleQuality() {
    setQuality((prev) => {
      const idx = QUALITY_CYCLE.indexOf(prev);
      return QUALITY_CYCLE[(idx + 1) % QUALITY_CYCLE.length];
    });
  }

  function cycleFormat() {
    setOutputFormat((fmt) => {
      const idx = FORMAT_CYCLE.indexOf(fmt);
      const next = FORMAT_CYCLE[(idx + 1) % FORMAT_CYCLE.length];
      if (next !== "pdf") setRemoveBlankPages(false);
      return next;
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
      payload.subject = emailSubject.trim() || null;
      payload.body = emailBody.trim() || null;
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

    if (isMultiStepFlatbed || forcePreview) {
      setStage("awaiting_next_page");
      busyLock.current = false;
      return;
    }

    await runDeliverStep(scanId);
  }

  return {
    source,
    setSource,
    scanDuplex,
    setScanDuplex,
    color,
    setColor,
    outputFormat,
    quality,
    removeBlankPages,
    setRemoveBlankPages,
    email,
    setEmail,
    emailSubject,
    setEmailSubject,
    emailBody,
    setEmailBody,
    fileName,
    setFileName,
    usbDrives,
    selectedUsbDevice,
    setSelectedUsbDevice,
    loadingDrives,
    fetchUsbDrives,
    stage,
    pendingScanId,
    scannedPages,
    previewPage,
    setPreviewPage,
    previewRev,
    rotatingPreview,
    cancelling,
    modal,
    setModal,
    hardwareBusy,
    isMultiStepFlatbed,
    cycleQuality,
    cycleFormat,
    cancelOperation,
    rotateCurrentPreviewPage,
    runDeliverStep,
    runScanPageStep,
  };
}
