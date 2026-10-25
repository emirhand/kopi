import { KioskButton } from "../../components/KioskButton";
import {
  FORMAT_META,
  QUALITY_META,
  type ScanFormat,
  type ScanQuality,
} from "./scanTypes";

interface ScanSettingsGridProps {
  source: "flatbed" | "adf";
  scanDuplex: boolean;
  color: boolean;
  outputFormat: ScanFormat;
  quality: ScanQuality;
  removeBlankPages: boolean;
  hardwareBusy: boolean;
  onToggleSource: () => void;
  onToggleDuplex: () => void;
  onToggleColor: () => void;
  onCycleFormat: () => void;
  onCycleQuality: () => void;
  onToggleRemoveBlankPages: () => void;
}

export function ScanSettingsGrid({
  source,
  scanDuplex,
  color,
  outputFormat,
  quality,
  removeBlankPages,
  hardwareBusy,
  onToggleSource,
  onToggleDuplex,
  onToggleColor,
  onCycleFormat,
  onCycleQuality,
  onToggleRemoveBlankPages,
}: ScanSettingsGridProps) {
  const currentQuality = QUALITY_META[quality];

  return (
    <div className="grid flex-1 grid-cols-2 gap-2.5 sm:grid-cols-3 md:gap-3">
      <KioskButton
        layout="tile"
        variant="industrial"
        tileActive={source === "adf"}
        className="min-h-[5.5rem]"
        disabled={hardwareBusy}
        onClick={onToggleSource}
      >
        <span>Source: {source === "flatbed" ? "Flatbed" : "ADF"}</span>
        <span className="mt-1 block text-[11px] font-medium normal-case tracking-normal text-zinc-400">
          {source === "flatbed" ? "Step-by-Step Scanner Glass" : "Automatic Document Feeder"}
        </span>
      </KioskButton>

      <KioskButton
        layout="tile"
        variant="industrial"
        tileActive={scanDuplex}
        className="min-h-[5.5rem]"
        disabled={hardwareBusy || source === "flatbed"}
        onClick={onToggleDuplex}
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

      <KioskButton
        layout="tile"
        variant="industrial"
        tileActive={color}
        className="min-h-[5.5rem]"
        disabled={hardwareBusy}
        onClick={onToggleColor}
      >
        <span>{color ? "Color" : "B&W"}</span>
        <span className="mt-1 block text-[11px] font-medium normal-case tracking-normal text-zinc-400">
          {color ? "Full Color Scan" : "Grayscale Scan"}
        </span>
      </KioskButton>

      <KioskButton
        layout="tile"
        variant="industrial"
        tileActive={outputFormat !== "pdf"}
        className="min-h-[5.5rem]"
        disabled={hardwareBusy}
        onClick={onCycleFormat}
      >
        <span>{FORMAT_META[outputFormat].label}</span>
        <span className="mt-1 block text-[11px] font-medium normal-case tracking-normal text-zinc-400">
          {FORMAT_META[outputFormat].subtitle}
        </span>
      </KioskButton>

      <KioskButton
        layout="tile"
        variant="industrial"
        tileActive={quality !== "high"}
        className="min-h-[5.5rem]"
        disabled={hardwareBusy}
        onClick={onCycleQuality}
      >
        <span>{currentQuality.label}</span>
        <span className="mt-1 block text-[11px] font-medium normal-case tracking-normal text-zinc-400">
          {currentQuality.subtitle}
        </span>
      </KioskButton>

      <KioskButton
        layout="tile"
        variant="industrial"
        tileActive={removeBlankPages && outputFormat === "pdf"}
        className="min-h-[5.5rem]"
        disabled={hardwareBusy || outputFormat !== "pdf"}
        onClick={onToggleRemoveBlankPages}
      >
        <span>Skip Blank: {outputFormat === "pdf" && removeBlankPages ? "ON" : "OFF"}</span>
        <span className="mt-1 block text-[11px] font-medium normal-case tracking-normal text-zinc-400">
          {outputFormat === "pdf" ? "Auto-remove empty pages" : "Available for PDF only"}
        </span>
      </KioskButton>
    </div>
  );
}
