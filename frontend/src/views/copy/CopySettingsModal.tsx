import {
  PAPER_SIZES,
  RESIZE_LABELS,
  type ContentTypeMode,
  type PageFlipMode,
  type PaperSizeOption,
  type ResizeMode,
} from "./copyTypes";

interface CopySettingsModalProps {
  open: boolean;
  lighterDarker: number;
  densitySummary: string;
  resizeMode: ResizeMode;
  resizePercent: number;
  originalSize: PaperSizeOption;
  paperSize: PaperSizeOption;
  pageFlip: PageFlipMode;
  collate: boolean;
  contentType: ContentTypeMode;
  savingDefaults: boolean;
  savedBanner: string | null;
  onClose: () => void;
  onSetLighterDarker: (val: number) => void;
  onSetResizeMode: (mode: ResizeMode) => void;
  onAdjustResizePercent: (delta: number) => void;
  onSetOriginalSize: (size: PaperSizeOption) => void;
  onSetPaperSize: (size: PaperSizeOption) => void;
  onSetPageFlip: (flip: PageFlipMode) => void;
  onSetCollate: (collate: boolean) => void;
  onSetContentType: (ct: ContentTypeMode) => void;
  onSaveDefaults: () => void;
  onResetFactoryDefaults: () => void;
}

export function CopySettingsModal({
  open,
  lighterDarker,
  densitySummary,
  resizeMode,
  resizePercent,
  originalSize,
  paperSize,
  pageFlip,
  collate,
  contentType,
  savingDefaults,
  savedBanner,
  onClose,
  onSetLighterDarker,
  onSetResizeMode,
  onAdjustResizePercent,
  onSetOriginalSize,
  onSetPaperSize,
  onSetPageFlip,
  onSetCollate,
  onSetContentType,
  onSaveDefaults,
  onResetFactoryDefaults,
}: CopySettingsModalProps) {
  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-3 md:p-6">
      <div className="flex max-h-[92dvh] w-full max-w-3xl flex-col overflow-hidden rounded-3xl border border-kiosk-industrial-border bg-kiosk-industrial-navy shadow-2xl">
        <div className="flex shrink-0 items-center justify-between border-b border-kiosk-industrial-border px-5 py-3.5">
          <div>
            <p className="text-[10px] font-semibold uppercase tracking-wider text-zinc-400">
              HP OfficeJet Pro 9010
            </p>
            <h2 className="text-xl font-black uppercase tracking-wide text-zinc-100">
              Copy Settings
            </h2>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-xl border border-kiosk-industrial-border bg-kiosk-industrial-slate px-4 py-2 text-sm font-black uppercase tracking-wider text-zinc-100 active:scale-95"
          >
            Done ✓
          </button>
        </div>

        <div className="flex-1 space-y-5 overflow-y-auto p-5">
          {/* 2.1 Lighter / Darker */}
          <section className="rounded-2xl border border-kiosk-industrial-border bg-kiosk-industrial-slate/60 p-4">
            <div className="flex items-center justify-between">
              <span className="text-sm font-black uppercase tracking-wider text-zinc-200">
                Lighter / Darker
              </span>
              <span className="font-mono text-sm font-bold text-amber-400">{densitySummary}</span>
            </div>
            <div className="mt-3 flex items-center gap-3">
              <button
                type="button"
                disabled={lighterDarker <= -4}
                onClick={() => onSetLighterDarker(Math.max(-4, lighterDarker - 1))}
                className="flex h-11 w-14 items-center justify-center rounded-xl border border-kiosk-industrial-border bg-kiosk-industrial-navy text-sm font-bold text-zinc-100 disabled:opacity-40 active:scale-95"
              >
                Lighter
              </button>
              <div className="grid flex-1 grid-cols-9 gap-1.5">
                {[-4, -3, -2, -1, 0, 1, 2, 3, 4].map((step) => (
                  <button
                    key={step}
                    type="button"
                    onClick={() => onSetLighterDarker(step)}
                    className={`flex h-10 items-center justify-center rounded-lg border text-xs font-bold transition ${
                      lighterDarker === step
                        ? "border-amber-400 bg-amber-500/30 text-amber-200"
                        : "border-kiosk-industrial-border bg-black/30 text-zinc-400"
                    }`}
                  >
                    {step > 0 ? `+${step}` : step}
                  </button>
                ))}
              </div>
              <button
                type="button"
                disabled={lighterDarker >= 4}
                onClick={() => onSetLighterDarker(Math.min(4, lighterDarker + 1))}
                className="flex h-11 w-14 items-center justify-center rounded-xl border border-kiosk-industrial-border bg-kiosk-industrial-navy text-sm font-bold text-zinc-100 disabled:opacity-40 active:scale-95"
              >
                Darker
              </button>
            </div>
          </section>

          {/* 2.2 Resize (Reduce / Enlarge) */}
          <section className="rounded-2xl border border-kiosk-industrial-border bg-kiosk-industrial-slate/60 p-4">
            <div className="flex items-center justify-between">
              <span className="text-sm font-black uppercase tracking-wider text-zinc-200">
                Resize
              </span>
              <span className="font-mono text-sm font-bold text-amber-400">
                {RESIZE_LABELS[resizeMode]}
                {resizeMode === "custom" ? ` (${resizePercent}%)` : ""}
              </span>
            </div>
            <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-3">
              {(Object.keys(RESIZE_LABELS) as ResizeMode[]).map((mode) => (
                <button
                  key={mode}
                  type="button"
                  onClick={() => onSetResizeMode(mode)}
                  className={`rounded-xl border px-3 py-2.5 text-xs font-bold uppercase tracking-wider transition ${
                    resizeMode === mode
                      ? "border-amber-400 bg-amber-500/25 text-amber-200"
                      : "border-kiosk-industrial-border bg-kiosk-industrial-navy text-zinc-300"
                  }`}
                >
                  {RESIZE_LABELS[mode]}
                </button>
              ))}
            </div>
            {resizeMode === "custom" && (
              <div className="mt-3 flex items-center justify-center gap-2 rounded-xl bg-black/30 p-2.5">
                {[-25, -5, -1].map((delta) => (
                  <button
                    key={delta}
                    type="button"
                    onClick={() => onAdjustResizePercent(delta)}
                    className="rounded-lg border border-kiosk-industrial-border bg-kiosk-industrial-navy px-3 py-1.5 text-xs font-bold text-zinc-200 active:scale-95"
                  >
                    {delta}%
                  </button>
                ))}
                <span className="min-w-[4.5rem] text-center font-mono text-lg font-black text-emerald-400">
                  {resizePercent}%
                </span>
                {[1, 5, 25].map((delta) => (
                  <button
                    key={delta}
                    type="button"
                    onClick={() => onAdjustResizePercent(delta)}
                    className="rounded-lg border border-kiosk-industrial-border bg-kiosk-industrial-navy px-3 py-1.5 text-xs font-bold text-zinc-200 active:scale-95"
                  >
                    +{delta}%
                  </button>
                ))}
              </div>
            )}
          </section>

          {/* 2.3 Original Size & Tray / Paper Size */}
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            <section className="rounded-2xl border border-kiosk-industrial-border bg-kiosk-industrial-slate/60 p-4">
              <span className="text-sm font-black uppercase tracking-wider text-zinc-200">
                Original Size
              </span>
              <div className="mt-2.5 flex flex-wrap gap-1.5">
                {PAPER_SIZES.map((sz) => (
                  <button
                    key={sz}
                    type="button"
                    onClick={() => onSetOriginalSize(sz)}
                    className={`rounded-xl border px-3 py-2 text-xs font-bold transition ${
                      originalSize === sz
                        ? "border-amber-400 bg-amber-500/25 text-amber-200"
                        : "border-kiosk-industrial-border bg-kiosk-industrial-navy text-zinc-300"
                    }`}
                  >
                    {sz}
                  </button>
                ))}
              </div>
            </section>

            <section className="rounded-2xl border border-kiosk-industrial-border bg-kiosk-industrial-slate/60 p-4">
              <span className="text-sm font-black uppercase tracking-wider text-zinc-200">
                Tray / Paper Size
              </span>
              <div className="mt-2.5 flex flex-wrap gap-1.5">
                {PAPER_SIZES.map((sz) => (
                  <button
                    key={sz}
                    type="button"
                    onClick={() => onSetPaperSize(sz)}
                    className={`rounded-xl border px-3 py-2 text-xs font-bold transition ${
                      paperSize === sz
                        ? "border-amber-400 bg-amber-500/25 text-amber-200"
                        : "border-kiosk-industrial-border bg-kiosk-industrial-navy text-zinc-300"
                    }`}
                  >
                    {sz}
                  </button>
                ))}
              </div>
            </section>
          </div>

          {/* 2.4 Two-Sided Page Flip, 2.5 Collate, 2.6 Content Enhancement */}
          <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
            <section className="rounded-2xl border border-kiosk-industrial-border bg-kiosk-industrial-slate/60 p-4">
              <span className="text-xs font-black uppercase tracking-wider text-zinc-200">
                Two-Sided Page Flip
              </span>
              <div className="mt-2.5 flex flex-col gap-1.5">
                <button
                  type="button"
                  onClick={() => onSetPageFlip("long_edge")}
                  className={`rounded-xl border px-3 py-2 text-left text-xs font-bold transition ${
                    pageFlip === "long_edge"
                      ? "border-amber-400 bg-amber-500/25 text-amber-200"
                      : "border-kiosk-industrial-border bg-kiosk-industrial-navy text-zinc-300"
                  }`}
                >
                  Book (Long Edge)
                </button>
                <button
                  type="button"
                  onClick={() => onSetPageFlip("short_edge")}
                  className={`rounded-xl border px-3 py-2 text-left text-xs font-bold transition ${
                    pageFlip === "short_edge"
                      ? "border-amber-400 bg-amber-500/25 text-amber-200"
                      : "border-kiosk-industrial-border bg-kiosk-industrial-navy text-zinc-300"
                  }`}
                >
                  Tablet (Short Edge)
                </button>
              </div>
            </section>

            <section className="rounded-2xl border border-kiosk-industrial-border bg-kiosk-industrial-slate/60 p-4">
              <span className="text-xs font-black uppercase tracking-wider text-zinc-200">
                Collate Copies
              </span>
              <div className="mt-2.5 flex flex-col gap-1.5">
                <button
                  type="button"
                  onClick={() => onSetCollate(true)}
                  className={`rounded-xl border px-3 py-2 text-left text-xs font-bold transition ${
                    collate
                      ? "border-amber-400 bg-amber-500/25 text-amber-200"
                      : "border-kiosk-industrial-border bg-kiosk-industrial-navy text-zinc-300"
                  }`}
                >
                  On (1-2-3, 1-2-3)
                </button>
                <button
                  type="button"
                  onClick={() => onSetCollate(false)}
                  className={`rounded-xl border px-3 py-2 text-left text-xs font-bold transition ${
                    !collate
                      ? "border-amber-400 bg-amber-500/25 text-amber-200"
                      : "border-kiosk-industrial-border bg-kiosk-industrial-navy text-zinc-300"
                  }`}
                >
                  Off (1-1, 2-2, 3-3)
                </button>
              </div>
            </section>

            <section className="rounded-2xl border border-kiosk-industrial-border bg-kiosk-industrial-slate/60 p-4">
              <span className="text-xs font-black uppercase tracking-wider text-zinc-200">
                Content Type
              </span>
              <div className="mt-2.5 flex flex-col gap-1.5">
                {(["mixed", "text", "photo"] as ContentTypeMode[]).map((ct) => (
                  <button
                    key={ct}
                    type="button"
                    onClick={() => onSetContentType(ct)}
                    className={`rounded-xl border px-3 py-1.5 text-left text-xs font-bold uppercase transition ${
                      contentType === ct
                        ? "border-amber-400 bg-amber-500/25 text-amber-200"
                        : "border-kiosk-industrial-border bg-kiosk-industrial-navy text-zinc-300"
                    }`}
                  >
                    {ct}
                  </button>
                ))}
              </div>
            </section>
          </div>
        </div>

        {/* 2.7 Save Current Settings as Default / Reset */}
        <div className="flex shrink-0 flex-wrap items-center justify-between gap-3 border-t border-kiosk-industrial-border bg-kiosk-industrial-slate/40 px-5 py-3">
          <div className="flex items-center gap-2">
            <button
              type="button"
              disabled={savingDefaults}
              onClick={onSaveDefaults}
              className="rounded-xl border border-amber-500/50 bg-amber-500/20 px-4 py-2 text-xs font-black uppercase tracking-wider text-amber-200 active:scale-95 disabled:opacity-40"
            >
              {savingDefaults ? "Saving…" : "Save as Default"}
            </button>
            <button
              type="button"
              disabled={savingDefaults}
              onClick={onResetFactoryDefaults}
              className="rounded-xl border border-kiosk-industrial-border bg-kiosk-industrial-navy px-4 py-2 text-xs font-bold uppercase tracking-wider text-zinc-300 active:scale-95 disabled:opacity-40"
            >
              Reset Factory Defaults
            </button>
            {savedBanner && (
              <span className="text-xs font-bold text-emerald-400">{savedBanner}</span>
            )}
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-xl bg-emerald-600 px-5 py-2 text-xs font-black uppercase tracking-wider text-white active:scale-95"
          >
            Apply & Close
          </button>
        </div>
      </div>
    </div>
  );
}
