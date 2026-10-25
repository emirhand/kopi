import { KioskButton } from "../../components/KioskButton";
import type { ScanDestination } from "./scanTypes";

interface ScanDestinationSelectorProps {
  onBack: () => void;
  onSelectDestination: (destination: ScanDestination) => void;
}

export function ScanDestinationSelector({
  onBack,
  onSelectDestination,
}: ScanDestinationSelectorProps) {
  return (
    <div className="flex h-[100dvh] w-[100dvw] flex-col overflow-hidden bg-kiosk-industrial-bezel text-zinc-100">
      <header className="flex shrink-0 items-center justify-between border-b border-kiosk-industrial-border bg-kiosk-industrial-navy px-4 py-3 md:px-8">
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={onBack}
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
          onClick={() => onSelectDestination("email")}
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
          onClick={() => onSelectDestination("usb")}
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
          onClick={() => onSelectDestination("archive")}
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
