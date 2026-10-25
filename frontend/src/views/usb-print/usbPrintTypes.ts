export interface UsbFileEntry {
  name: string;
  rel_path: string;
  is_dir: boolean;
  ext: string;
  size_bytes: number;
  size_label: string;
  pages: number;
}

export type PrintSidesMode = "one_sided" | "two_sided_book" | "two_sided_tablet";
export type QualityMode = "draft" | "normal" | "best";
export type PaperSizeOption = "A4" | "Letter" | "Legal" | "A5" | "4x6";

export const SIDES_CYCLE: readonly PrintSidesMode[] = [
  "one_sided",
  "two_sided_book",
  "two_sided_tablet",
];

export const SIDES_META: Record<
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

export const QUALITY_CYCLE: readonly QualityMode[] = ["draft", "normal", "best"];
export const PAPER_SIZES: readonly PaperSizeOption[] = ["A4", "Letter", "Legal", "A5", "4x6"];

export function fileIcon(entry: UsbFileEntry): string {
  if (entry.is_dir) return "📁";
  if (entry.ext === "pdf") return "📄";
  if (entry.ext === "txt") return "📝";
  return "🖼️";
}
