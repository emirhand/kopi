import { KioskButton } from "../../components/KioskButton";
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

interface UsbPrintPreviewAndOptionsProps {
  selectedFile: UsbFileEntry;
  previewPage: number;
  previewUrl: string;
  copies: number;
  sidesMode: PrintSidesMode;
  color: boolean;
  quality: QualityMode;
  paperSize: PaperSizeOption;
  fitToPage: boolean;
  collate: boolean;
  onPrevPage: () => void;
  onNextPage: () => void;
  onCycleSides: () => void;
  onToggleColor: () => void;
  onCycleQuality: () => void;
  onCyclePaperSize: () => void;
  onToggleFitToPage: () => void;
  onToggleCollate: () => void;
  onStartPrint: () => void;
  onChooseDifferentFile: () => void;
}

export function UsbPrintPreviewAndOptions({
  selectedFile,
  previewPage,
  previewUrl,
  copies,
  sidesMode,
  color,
  quality,
  paperSize,
  fitToPage,
  collate,
  onPrevPage,
  onNextPage,
  onCycleSides,
  onToggleColor,
  onCycleQuality,
  onCyclePaperSize,
  onToggleFitToPage,
  onToggleCollate,
  onStartPrint,
  onChooseDifferentFile,
}: UsbPrintPreviewAndOptionsProps) {
  void SIDES_CYCLE;
  void QUALITY_CYCLE;
  void PAPER_SIZES;

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-4 md:flex-row md:items-stretch">
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
            src={previewUrl}
            alt={`Preview of ${selectedFile.name}`}
            className="max-h-full max-w-full rounded object-contain shadow-lg"
          />
        </div>

        {selectedFile.pages > 1 && (
          <div className="mt-2 flex items-center gap-3 pt-1">
            <button
              type="button"
              disabled={previewPage <= 0}
              onClick={onPrevPage}
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
              onClick={onNextPage}
              className="rounded-lg border border-kiosk-industrial-border bg-kiosk-industrial-navy px-3 py-1 text-xs font-bold text-zinc-200 disabled:opacity-30 active:scale-95"
            >
              Next ▶
            </button>
          </div>
        )}
      </div>

      <div className="flex flex-col justify-between gap-3 md:w-80">
        <div className="grid grid-cols-2 gap-2">
          <KioskButton
            layout="tile"
            variant="industrial"
            tileActive={sidesMode !== "one_sided"}
            className="min-h-[4.75rem]"
            onClick={onCycleSides}
          >
            <span className="text-sm">{SIDES_META[sidesMode].label}</span>
            <span className="mt-0.5 block text-[10px] font-medium normal-case text-zinc-400">
              {SIDES_META[sidesMode].subtitle}
            </span>
          </KioskButton>

          <KioskButton
            layout="tile"
            variant="industrial"
            tileActive={color}
            className="min-h-[4.75rem]"
            onClick={onToggleColor}
          >
            <span className="text-sm">{color ? "Color" : "B&W"}</span>
            <span className="mt-0.5 block text-[10px] font-medium normal-case text-zinc-400">
              {color ? "Full Color" : "Grayscale"}
            </span>
          </KioskButton>

          <KioskButton
            layout="tile"
            variant="industrial"
            tileActive={quality !== "normal"}
            className="min-h-[4.75rem]"
            onClick={onCycleQuality}
          >
            <span className="text-sm uppercase">Quality: {quality}</span>
            <span className="mt-0.5 block text-[10px] font-medium normal-case text-zinc-400">
              Tap to cycle
            </span>
          </KioskButton>

          <KioskButton
            layout="tile"
            variant="industrial"
            tileActive={paperSize !== "A4"}
            className="min-h-[4.75rem]"
            onClick={onCyclePaperSize}
          >
            <span className="text-sm">Paper: {paperSize}</span>
            <span className="mt-0.5 block text-[10px] font-medium normal-case text-zinc-400">
              Tap to cycle
            </span>
          </KioskButton>

          <KioskButton
            layout="tile"
            variant="industrial"
            tileActive={fitToPage}
            className="min-h-[4.75rem]"
            onClick={onToggleFitToPage}
          >
            <span className="text-sm">{fitToPage ? "Fit to Page" : "Actual 100%"}</span>
            <span className="mt-0.5 block text-[10px] font-medium normal-case text-zinc-400">
              Page Scaling
            </span>
          </KioskButton>

          <KioskButton
            layout="tile"
            variant="industrial"
            tileActive={collate && copies > 1}
            className="min-h-[4.75rem]"
            disabled={copies <= 1}
            onClick={onToggleCollate}
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
            onClick={onStartPrint}
          >
            🖨️ Print ({copies})
          </KioskButton>
          <button
            type="button"
            onClick={onChooseDifferentFile}
            className="rounded-xl border border-kiosk-industrial-border bg-kiosk-industrial-navy py-2.5 text-xs font-bold uppercase tracking-wider text-zinc-300 active:scale-95"
          >
            ← Choose Different File
          </button>
        </div>
      </div>
    </div>
  );
}
