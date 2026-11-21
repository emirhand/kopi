import { KioskButton } from "../../components/KioskButton";

interface CopyModeSelectorProps {
  onBack: () => void;
  onSelectDocument: () => void;
  onSelectIdCard: () => void;
  onSelectPhoto: () => void;
}

export function CopyModeSelector({
  onBack,
  onSelectDocument,
  onSelectIdCard,
  onSelectPhoto,
}: CopyModeSelectorProps) {
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
          onClick={onSelectDocument}
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
          onClick={onSelectIdCard}
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
          onClick={onSelectPhoto}
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
