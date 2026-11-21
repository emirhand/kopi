export type ScanDestination = "email" | "usb" | "archive";
export type Stage = "idle" | "scanning" | "awaiting_next_page" | "delivering" | "done" | "error";
export type ScanFormat = "pdf" | "jpg" | "png" | "tiff";
export type ScanQuality = "standard" | "high" | "best";

export const FORMAT_CYCLE: readonly ScanFormat[] = ["pdf", "jpg", "png", "tiff"];

export const FORMAT_META: Record<ScanFormat, { label: string; subtitle: string }> = {
  pdf: { label: "Format: PDF", subtitle: "Multi-Page Document (.pdf)" },
  jpg: { label: "Format: JPG", subtitle: "Photo / 1 File per Page (.jpg)" },
  png: { label: "Format: PNG", subtitle: "Lossless / 1 File per Page (.png)" },
  tiff: { label: "Format: TIFF", subtitle: "Archival Multi-Page (.tiff)" },
};

export const QUALITY_CYCLE: readonly ScanQuality[] = ["standard", "high", "best"];

export const QUALITY_META: Record<
  ScanQuality,
  { label: string; subtitle: string; dpi: 150 | 300 | 600 }
> = {
  standard: { label: "Draft (150 DPI)", subtitle: "Smaller File • Fast", dpi: 150 },
  high: { label: "Normal (300 DPI)", subtitle: "Standard Document", dpi: 300 },
  best: { label: "Best (600 DPI)", subtitle: "High Detail", dpi: 600 },
};

export const DESTINATION_META: Record<
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
