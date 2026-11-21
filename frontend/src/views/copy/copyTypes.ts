import type { CSSProperties } from "react";

export type Stage = "idle" | "scanning" | "awaiting_next_page" | "printing" | "done" | "error";

export type SidedMode = "1_to_1" | "1_to_2" | "2_to_2" | "2_to_1";
export type QualityMode = "draft" | "normal" | "best";
export type ResizeMode = "actual" | "fit_to_page" | "full_page_91" | "two_on_one" | "custom";
export type PaperSizeOption = "A4" | "Letter" | "Legal" | "A5" | "4x6";
export type PageFlipMode = "long_edge" | "short_edge";
export type ContentTypeMode = "mixed" | "text" | "photo";

export const SIDED_CYCLE: readonly SidedMode[] = ["1_to_1", "1_to_2", "2_to_2", "2_to_1"];
export const QUALITY_CYCLE: readonly QualityMode[] = ["draft", "normal", "best"];
export const PAPER_SIZES: readonly PaperSizeOption[] = ["A4", "Letter", "Legal", "A5", "4x6"];

export const SIDED_META: Record<
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

export const QUALITY_META: Record<
  QualityMode,
  { label: string; subtitle: string; dpi: 150 | 300 | 600 }
> = {
  draft: { label: "Draft", subtitle: "Fast • 150 DPI", dpi: 150 },
  normal: { label: "Normal", subtitle: "Standard • 300 DPI", dpi: 300 },
  best: { label: "Best", subtitle: "High Detail • 600 DPI", dpi: 600 },
};

export const RESIZE_LABELS: Record<ResizeMode, string> = {
  actual: "Actual (100%)",
  fit_to_page: "Fit to Page",
  full_page_91: "Full Page (91%)",
  two_on_one: "2 Pages on 1 Sheet",
  custom: "Custom %",
};

export const GRID_STYLE: CSSProperties = {
  width: "min(92vw, calc((100dvh - 10rem) * 3 / 2))",
  height:
    "min(calc(100dvh - 10rem), calc(min(92vw, (100dvh - 10rem) * 3 / 2) * 2 / 3))",
};

export interface CopyDefaultsPayload {
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

export const FACTORY_DEFAULTS: CopyDefaultsPayload = {
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
