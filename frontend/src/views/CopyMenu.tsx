import { useNavigate, useParams } from "react-router-dom";
import { KioskButton } from "../components/KioskButton";
import { ProgressBar } from "../components/ProgressBar";
import { ScannedPagePreviewCard } from "../components/ScannedPagePreviewCard";
import { CopiesKeypadModal } from "./copy/CopiesKeypadModal";
import { CopyModeSelector } from "./copy/CopyModeSelector";
import { CopySettingsModal } from "./copy/CopySettingsModal";
import { GRID_STYLE } from "./copy/copyTypes";
import { useCopyController } from "./copy/useCopyController";

export function CopyMenu() {
  const nav = useNavigate();
  const { mode: rawMode } = useParams<{ mode?: string }>();
  const copyMode: "document" | "photo" | null =
    rawMode === "document" || rawMode === "photo" ? rawMode : null;

  const ctrl = useCopyController(copyMode);

  function selectQuickPreset(preset: "document" | "photo") {
    if (preset === "photo") {
      ctrl.setContentType("photo");
      ctrl.setQuality("best");
      ctrl.setColor(true);
      nav("/copy/photo", { replace: true });
    } else {
      ctrl.setContentType("mixed");
      ctrl.setQuality("normal");
      nav("/copy/document", { replace: true });
    }
  }

  if (!copyMode) {
    return (
      <CopyModeSelector
        onBack={() => nav("/")}
        onSelectDocument={() => nav("/copy/document")}
        onSelectIdCard={() => nav("/id-scan")}
        onSelectPhoto={() => nav("/copy/photo")}
      />
    );
  }

  const previewDescription =
    ctrl.source === "flatbed"
      ? ctrl.currentSided.scanDuplex
        ? "Flip the document over (or place the next page) on the glass to add another page, or tap Finish & Print."
        : "Place the next page on the scanner glass to add it to this copy job, or tap Finish & Print."
      : "Review the scanned document pages before sending to the printer.";

  return (
    <div className="flex h-[100dvh] w-[100dvw] flex-col overflow-hidden bg-kiosk-industrial-bezel text-zinc-100">
      <header className="flex shrink-0 items-center justify-between gap-2 border-b border-kiosk-industrial-border bg-kiosk-industrial-navy px-3 py-2 md:px-6">
        <div className="flex items-center gap-3">
          <button
            type="button"
            disabled={ctrl.hardwareBusy}
            onClick={() => nav("/copy")}
            className="flex h-11 items-center justify-center rounded-xl border border-kiosk-industrial-border bg-kiosk-industrial-slate px-3.5 text-sm font-black uppercase tracking-wider text-zinc-100 disabled:opacity-40 active:scale-95"
          >
            ← Back
          </button>
          <div>
            <p className="text-[10px] font-semibold uppercase tracking-wider text-zinc-500">
              HP 9010 Copier
            </p>
            <h1 className="text-lg font-black uppercase tracking-wide text-zinc-100 md:text-2xl">
              {copyMode === "photo" ? "Photo Copy" : "Document Copy"}
            </h1>
          </div>
        </div>

        <div className="hidden items-center gap-1.5 rounded-xl border border-kiosk-industrial-border bg-kiosk-industrial-slate/60 p-1 sm:flex">
          <button
            type="button"
            disabled={ctrl.hardwareBusy}
            onClick={() => selectQuickPreset("document")}
            className={`rounded-lg px-3 py-1.5 text-xs font-bold uppercase tracking-wider transition ${
              ctrl.contentType !== "photo"
                ? "bg-amber-500/20 text-amber-300 ring-1 ring-amber-500/50"
                : "text-zinc-400 hover:text-zinc-200"
            }`}
          >
            Document
          </button>
          <button
            type="button"
            disabled={ctrl.hardwareBusy}
            onClick={() => selectQuickPreset("photo")}
            className={`rounded-lg px-3 py-1.5 text-xs font-bold uppercase tracking-wider transition ${
              ctrl.contentType === "photo"
                ? "bg-amber-500/20 text-amber-300 ring-1 ring-amber-500/50"
                : "text-zinc-400 hover:text-zinc-200"
            }`}
          >
            Photo
          </button>
          <button
            type="button"
            disabled={ctrl.hardwareBusy}
            onClick={() => nav("/id-scan")}
            className="rounded-lg px-3 py-1.5 text-xs font-bold uppercase tracking-wider text-zinc-400 transition hover:text-zinc-200"
          >
            ID Card ↗
          </button>
        </div>

        <div className="flex items-center gap-2">
          {ctrl.stage === "idle" && (
            <button
              type="button"
              disabled={ctrl.hardwareBusy}
              onClick={() => void ctrl.startPreview()}
              className="flex h-11 items-center gap-1.5 rounded-xl border border-amber-500/40 bg-amber-500/15 px-3.5 text-xs font-black uppercase tracking-wider text-amber-300 disabled:opacity-40 active:scale-95"
              title="Scan and preview before printing"
            >
              🔍 Preview
            </button>
          )}
          <div className="flex items-center gap-1.5 rounded-xl border border-kiosk-industrial-border bg-kiosk-industrial-slate/70 px-2.5 py-1.5">
            <span className="mr-1 hidden text-xs font-semibold uppercase tracking-wider text-zinc-400 md:inline">
              Copies
            </span>
            <button
              type="button"
              disabled={ctrl.hardwareBusy || ctrl.copies <= 1}
              onClick={() => ctrl.adjustCopies(-1)}
              className="flex h-9 w-9 items-center justify-center rounded-lg border border-kiosk-industrial-border bg-kiosk-industrial-navy text-xl font-bold text-zinc-100 disabled:opacity-40 active:scale-95"
              aria-label="Decrease copies"
            >
              −
            </button>
            <button
              type="button"
              disabled={ctrl.hardwareBusy}
              onClick={() => {
                ctrl.setKeypadBuffer(String(ctrl.copies));
                ctrl.setCopiesKeypadOpen(true);
              }}
              className="min-w-[2.75rem] rounded-lg px-1.5 py-0.5 text-center font-mono text-2xl font-black tabular-nums text-emerald-400 hover:bg-white/5 active:scale-95"
              title="Tap to enter copy count"
            >
              {ctrl.copies}
            </button>
            <button
              type="button"
              disabled={ctrl.hardwareBusy || ctrl.copies >= 99}
              onClick={() => ctrl.adjustCopies(1)}
              className="flex h-9 w-9 items-center justify-center rounded-lg border border-kiosk-industrial-border bg-kiosk-industrial-navy text-xl font-bold text-zinc-100 disabled:opacity-40 active:scale-95"
              aria-label="Increase copies"
            >
              +
            </button>
          </div>
        </div>
      </header>

      <main className="flex min-h-0 flex-1 items-center justify-center px-3 py-2 md:px-6">
        {(ctrl.stage === "scanning" || ctrl.stage === "printing") && (
          <div className="flex w-full max-w-xl flex-col items-center gap-6 px-2">
            <div className="w-full">
              {ctrl.stage === "scanning" ? (
                <ProgressBar
                  label={
                    ctrl.isMultiPageFlatbed
                      ? `Scanning Page ${ctrl.scannedPages + 1} from Flatbed…`
                      : "Scanning…"
                  }
                  variant="scan"
                />
              ) : (
                <ProgressBar
                  label={`Printing ${ctrl.copies} ${ctrl.copies === 1 ? "copy" : "copies"}…`}
                  variant="print"
                />
              )}
            </div>
            <KioskButton
              variant="industrial"
              className="min-h-[4rem] w-full max-w-xs border-2 border-red-500/70 bg-red-950/60 text-xl font-black uppercase tracking-wider text-red-200 ring-2 ring-red-500/30"
              disabled={ctrl.cancelling}
              onClick={() => void ctrl.cancelOperation()}
            >
              {ctrl.cancelling ? "Stopping…" : "Stop / Cancel"}
            </KioskButton>
          </div>
        )}

        {ctrl.stage === "awaiting_next_page" && ctrl.pendingScanId && (
          <ScannedPagePreviewCard
            pendingScanId={ctrl.pendingScanId}
            scannedPages={ctrl.scannedPages}
            previewPage={ctrl.previewPage}
            previewRev={ctrl.previewRev}
            rotatingPreview={ctrl.rotatingPreview}
            headerBadge={`Copy Preview (${ctrl.currentSided.title})`}
            headingText={`${ctrl.scannedPages} ${ctrl.scannedPages === 1 ? "Page" : "Pages"} Ready`}
            descriptionText={previewDescription}
            showAddPageButton={ctrl.source === "flatbed"}
            finishLabel={`Finish & Print (${ctrl.copies})`}
            cancelLabel="Cancel Job"
            onRotate={() => void ctrl.rotateCurrentPreviewPage()}
            onPrevPage={() => ctrl.setPreviewPage((p) => Math.max(0, p - 1))}
            onNextPage={() =>
              ctrl.setPreviewPage((p) => Math.min(ctrl.scannedPages - 1, p + 1))
            }
            onAddPage={() => void ctrl.runScanStep(ctrl.pendingScanId, true)}
            onFinish={() => void ctrl.runPrintStep(ctrl.pendingScanId!)}
            onCancel={() => void ctrl.cancelOperation()}
          />
        )}

        {ctrl.stage === "done" && (
          <div className="flex max-w-xl flex-col items-center rounded-3xl border-2 border-emerald-500/40 bg-kiosk-industrial-slate/80 p-8 text-center shadow-xl">
            <p className="text-3xl font-black text-zinc-100 md:text-4xl">Done</p>
            <p className="mt-3 text-lg text-zinc-400">
              Submitted {ctrl.copies} {ctrl.copies === 1 ? "copy" : "copies"} to printer.
            </p>
          </div>
        )}

        {ctrl.stage === "error" && ctrl.errorDetail && (
          <div className="max-h-[min(70dvh,28rem)] w-full max-w-xl overflow-auto rounded-3xl border-2 border-red-500/50 bg-kiosk-industrial-slate/90 p-6 shadow-xl">
            <p className="text-2xl font-black text-zinc-100 select-text">Check hardware</p>
            <p className="mt-3 whitespace-pre-wrap rounded-xl bg-black/30 p-3 font-mono text-sm leading-snug text-zinc-300 select-text cursor-text">
              {ctrl.errorDetail}
            </p>
            <div className="mt-6 flex flex-wrap justify-center gap-3">
              <KioskButton
                variant="industrialMuted"
                className="min-h-[3.5rem] flex-1 text-base"
                onClick={() => void ctrl.copyErrorToClipboard()}
              >
                {ctrl.copiedError ? "Copied!" : "Copy Error"}
              </KioskButton>
              {ctrl.pendingScanId && (
                <KioskButton
                  variant="primary"
                  className="min-h-[3.5rem] flex-1 text-lg"
                  onClick={() => {
                    ctrl.setErrorDetail(null);
                    void ctrl.runPrintStep(ctrl.pendingScanId!);
                  }}
                >
                  Retry Print
                </KioskButton>
              )}
              <KioskButton
                variant="industrial"
                className="min-h-[3.5rem] flex-1 text-lg"
                onClick={() => ctrl.resetFromError(true)}
              >
                Back to Options
              </KioskButton>
            </div>
          </div>
        )}

        {ctrl.stage === "idle" && (
          <div
            className="grid min-h-0 grid-cols-3 grid-rows-2 gap-3 md:gap-4"
            style={GRID_STYLE}
          >
            <KioskButton
              layout="tile"
              variant="industrial"
              tileActive={ctrl.sidedMode !== "1_to_1"}
              className="min-h-0 min-w-0"
              disabled={ctrl.hardwareBusy}
              onClick={ctrl.cycleSidedMode}
            >
              <span>{ctrl.currentSided.title}</span>
              <span className="mt-1 block text-[11px] font-medium normal-case tracking-normal text-zinc-400">
                {ctrl.currentSided.subtitle}
              </span>
            </KioskButton>

            <KioskButton
              layout="tile"
              variant="industrial"
              tileActive={ctrl.color}
              className="min-h-0 min-w-0"
              disabled={ctrl.hardwareBusy}
              onClick={() => ctrl.setColor((c) => !c)}
            >
              <span>{ctrl.color ? "Color" : "B&W"}</span>
              <span className="mt-1 block text-[11px] font-medium normal-case tracking-normal text-zinc-400">
                {ctrl.color ? "Full Color" : "Grayscale"}
              </span>
            </KioskButton>

            <KioskButton
              layout="tile"
              variant="industrial"
              tileActive={ctrl.source === "adf"}
              className="min-h-0 min-w-0"
              disabled={ctrl.hardwareBusy}
              onClick={() => ctrl.setSource((s) => (s === "flatbed" ? "adf" : "flatbed"))}
            >
              <span>{ctrl.effectiveSourceLabel}</span>
              <span className="mt-1 block text-[11px] font-medium normal-case tracking-normal text-zinc-400">
                {ctrl.isMultiPageFlatbed ? "Step-by-Step Glass Scan" : "Source (Tap to Switch)"}
              </span>
            </KioskButton>

            <KioskButton
              layout="tile"
              variant="industrial"
              tileActive={ctrl.quality !== "normal"}
              className="min-h-0 min-w-0"
              disabled={ctrl.hardwareBusy}
              onClick={ctrl.cycleQuality}
            >
              <span>{ctrl.currentQuality.label}</span>
              <span className="mt-1 block text-[11px] font-medium normal-case tracking-normal text-zinc-400">
                {ctrl.currentQuality.subtitle}
              </span>
            </KioskButton>

            <KioskButton
              layout="tile"
              variant="industrial"
              tileActive={ctrl.hasCustomAdvanced}
              className="min-h-0 min-w-0"
              disabled={ctrl.hardwareBusy}
              onClick={() => ctrl.setSettingsOpen(true)}
            >
              <span>⚙️ Settings</span>
              <span className="mt-1 block text-[11px] font-medium normal-case tracking-normal text-zinc-400">
                {ctrl.resizeSummary} • {ctrl.densitySummary} • {ctrl.paperSize}
              </span>
            </KioskButton>

            <KioskButton
              layout="tile"
              variant="industrial"
              className="min-h-0 min-w-0 ring-1 ring-amber-500/30"
              disabled={ctrl.hardwareBusy}
              onClick={() => void ctrl.startCopy()}
            >
              Start ({ctrl.copies})
            </KioskButton>
          </div>
        )}
      </main>

      <CopiesKeypadModal
        open={ctrl.copiesKeypadOpen}
        buffer={ctrl.keypadBuffer}
        onChangeBuffer={ctrl.setKeypadBuffer}
        onClose={() => ctrl.setCopiesKeypadOpen(false)}
        onConfirm={() => {
          const parsed = parseInt(ctrl.keypadBuffer, 10);
          if (!Number.isNaN(parsed) && parsed >= 1) {
            ctrl.setCopies(Math.min(99, parsed));
          }
          ctrl.setCopiesKeypadOpen(false);
        }}
      />

      <CopySettingsModal
        open={ctrl.settingsOpen}
        lighterDarker={ctrl.lighterDarker}
        densitySummary={ctrl.densitySummary}
        resizeMode={ctrl.resizeMode}
        resizePercent={ctrl.resizePercent}
        originalSize={ctrl.originalSize}
        paperSize={ctrl.paperSize}
        pageFlip={ctrl.pageFlip}
        collate={ctrl.collate}
        contentType={ctrl.contentType}
        savingDefaults={ctrl.savingDefaults}
        savedBanner={ctrl.savedBanner}
        onClose={() => ctrl.setSettingsOpen(false)}
        onSetLighterDarker={ctrl.setLighterDarker}
        onSetResizeMode={ctrl.setResizeMode}
        onAdjustResizePercent={(delta) =>
          ctrl.setResizePercent((p) => Math.max(25, Math.min(400, p + delta)))
        }
        onSetOriginalSize={ctrl.setOriginalSize}
        onSetPaperSize={ctrl.setPaperSize}
        onSetPageFlip={ctrl.setPageFlip}
        onSetCollate={ctrl.setCollate}
        onSetContentType={ctrl.setContentType}
        onSaveDefaults={() => void ctrl.saveCurrentAsDefaults()}
        onResetFactoryDefaults={() => void ctrl.resetToFactoryDefaults()}
      />
    </div>
  );
}
