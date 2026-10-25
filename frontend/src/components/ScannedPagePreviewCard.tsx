import { apiUrl } from "../api";
import { KioskButton } from "./KioskButton";

interface ScannedPagePreviewCardProps {
  pendingScanId: string;
  scannedPages: number;
  previewPage: number;
  previewRev: number;
  rotatingPreview: boolean;
  headerBadge: string;
  headingText: string;
  descriptionText: string;
  showAddPageButton: boolean;
  finishLabel: string;
  cancelLabel: string;
  onRotate: () => void;
  onPrevPage: () => void;
  onNextPage: () => void;
  onAddPage: () => void;
  onFinish: () => void;
  onCancel: () => void;
}

export function ScannedPagePreviewCard({
  pendingScanId,
  scannedPages,
  previewPage,
  previewRev,
  rotatingPreview,
  headerBadge,
  headingText,
  descriptionText,
  showAddPageButton,
  finishLabel,
  cancelLabel,
  onRotate,
  onPrevPage,
  onNextPage,
  onAddPage,
  onFinish,
  onCancel,
}: ScannedPagePreviewCardProps) {
  return (
    <div className="my-auto flex max-h-full w-full max-w-4xl flex-col gap-4 self-center rounded-3xl border-2 border-amber-500/50 bg-kiosk-industrial-slate/95 p-4 shadow-2xl md:flex-row md:items-stretch md:p-6">
      <div className="flex flex-1 flex-col items-center justify-between rounded-2xl border border-kiosk-industrial-border bg-black/50 p-3">
        <div className="flex w-full items-center justify-between px-1 pb-2">
          <span className="text-xs font-bold uppercase tracking-wider text-zinc-400">
            Page {previewPage + 1} of {scannedPages}
          </span>
          <button
            type="button"
            disabled={rotatingPreview}
            onClick={onRotate}
            className="rounded-lg border border-kiosk-industrial-border bg-kiosk-industrial-navy px-3 py-1 text-xs font-bold uppercase tracking-wider text-zinc-200 active:scale-95 disabled:opacity-40"
          >
            {rotatingPreview ? "Rotating…" : "↻ Rotate 90°"}
          </button>
        </div>

        <div className="flex max-h-[42dvh] min-h-[12rem] w-full flex-1 items-center justify-center overflow-hidden rounded-xl bg-zinc-900/80 p-2 md:max-h-[52dvh]">
          <img
            src={apiUrl(
              `/api/copy/preview/${encodeURIComponent(pendingScanId)}?page=${previewPage}&r=${previewRev}`
            )}
            alt={`Scanned page ${previewPage + 1}`}
            className="max-h-full max-w-full rounded object-contain shadow-lg"
          />
        </div>

        {scannedPages > 1 && (
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
              {previewPage + 1} / {scannedPages}
            </span>
            <button
              type="button"
              disabled={previewPage >= scannedPages - 1}
              onClick={onNextPage}
              className="rounded-lg border border-kiosk-industrial-border bg-kiosk-industrial-navy px-3 py-1 text-xs font-bold text-zinc-200 disabled:opacity-30 active:scale-95"
            >
              Next ▶
            </button>
          </div>
        )}
      </div>

      <div className="flex flex-col justify-between gap-3 md:w-72">
        <div>
          <p className="text-xs font-bold uppercase tracking-widest text-amber-400">{headerBadge}</p>
          <h2 className="mt-1 text-2xl font-black text-zinc-100">{headingText}</h2>
          <p className="mt-2 text-sm leading-snug text-zinc-300">{descriptionText}</p>
        </div>

        <div className="flex flex-col gap-2.5">
          {showAddPageButton && (
            <KioskButton
              variant="industrial"
              className="min-h-[3.75rem] w-full text-base ring-1 ring-amber-500/40"
              onClick={onAddPage}
            >
              + Scan Page {scannedPages + 1}
            </KioskButton>
          )}
          <KioskButton variant="primary" className="min-h-[4rem] w-full text-lg" onClick={onFinish}>
            {finishLabel}
          </KioskButton>
          <button
            type="button"
            onClick={onCancel}
            className="mt-1 rounded-xl border border-red-500/40 bg-red-950/40 py-2.5 text-sm font-bold uppercase tracking-wider text-red-300 active:scale-95"
          >
            {cancelLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
