import { useCallback, useEffect, useRef, useState } from "react";
import { apiUrl, parseErrorDetail } from "../../api";
import { useUsbDrives } from "../../hooks/useUsbDrives";
import {
  PAPER_SIZES,
  QUALITY_CYCLE,
  SIDES_CYCLE,
  SIDES_META,
  type PaperSizeOption,
  type PrintSidesMode,
  type QualityMode,
  type UsbFileEntry,
} from "./usbPrintTypes";

export function useUsbPrintController() {
  const {
    usbDrives,
    selectedDevice,
    setSelectedDevice,
    selectedDrive,
    loadingDrives,
    fetchDrives,
  } = useUsbDrives(true);

  const [subpath, setSubpath] = useState<string>("");
  const [entries, setEntries] = useState<UsbFileEntry[]>([]);
  const [loadingFiles, setLoadingFiles] = useState(false);
  const [selectedFile, setSelectedFile] = useState<UsbFileEntry | null>(null);
  const [previewPage, setPreviewPage] = useState<number>(0);

  const [copies, setCopies] = useState<number>(1);
  const [sidesMode, setSidesMode] = useState<PrintSidesMode>("one_sided");
  const [color, setColor] = useState<boolean>(true);
  const [quality, setQuality] = useState<QualityMode>("normal");
  const [paperSize, setPaperSize] = useState<PaperSizeOption>("A4");
  const [fitToPage, setFitToPage] = useState<boolean>(true);
  const [collate, setCollate] = useState<boolean>(true);

  const [printing, setPrinting] = useState<boolean>(false);
  const [cancelling, setCancelling] = useState<boolean>(false);
  const [modal, setModal] = useState<{
    title: string;
    message: string;
    variant?: "info" | "error";
  } | null>(null);
  const busyRef = useRef(false);

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

  function cycleSides() {
    setSidesMode((prev) => {
      const idx = SIDES_CYCLE.indexOf(prev);
      return SIDES_CYCLE[(idx + 1) % SIDES_CYCLE.length];
    });
  }

  function cycleQuality() {
    setQuality((prev) => {
      const idx = QUALITY_CYCLE.indexOf(prev);
      return QUALITY_CYCLE[(idx + 1) % QUALITY_CYCLE.length];
    });
  }

  function cyclePaperSize() {
    setPaperSize((prev) => {
      const idx = PAPER_SIZES.indexOf(prev);
      return PAPER_SIZES[(idx + 1) % PAPER_SIZES.length];
    });
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

  return {
    usbDrives,
    selectedDevice,
    setSelectedDevice,
    loadingDrives,
    fetchDrives,
    subpath,
    entries,
    loadingFiles,
    selectedFile,
    setSelectedFile,
    previewPage,
    setPreviewPage,
    copies,
    setCopies,
    sidesMode,
    color,
    setColor,
    quality,
    paperSize,
    fitToPage,
    setFitToPage,
    collate,
    setCollate,
    printing,
    cancelling,
    modal,
    setModal,
    openFolder,
    navigateUpFolder,
    selectPrintableFile,
    cycleSides,
    cycleQuality,
    cyclePaperSize,
    cancelPrint,
    startPrint,
    buildPreviewUrl,
  };
}
