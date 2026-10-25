import { useNavigate, useParams } from "react-router-dom";
import { KioskButton } from "../components/KioskButton";
import { ProgressBar } from "../components/ProgressBar";
import { ScannedPagePreviewCard } from "../components/ScannedPagePreviewCard";
import { StatusModal } from "../components/StatusModal";
import { ScanDestinationHeader } from "./scan/ScanDestinationHeader";
import { ScanDestinationSelector } from "./scan/ScanDestinationSelector";
import { ScanSettingsGrid } from "./scan/ScanSettingsGrid";
import { DESTINATION_META, type ScanDestination } from "./scan/scanTypes";
import { useScanController } from "./scan/useScanController";

export function ScanMenu() {
  const nav = useNavigate();
  const { destination: rawDest } = useParams<{ destination?: string }>();
  const destination: ScanDestination | null =
    rawDest === "email" || rawDest === "usb" || rawDest === "archive" ? rawDest : null;

  const ctrl = useScanController(destination);

  if (!destination) {
    return (
      <ScanDestinationSelector
        onBack={() => nav("/")}
        onSelectDestination={(dest) => nav(`/scan/${dest}`)}
      />
    );
  }

  const destMeta = DESTINATION_META[destination];
  const previewDescription =
    ctrl.source === "flatbed"
      ? ctrl.outputFormat === "jpg" || ctrl.outputFormat === "png"
        ? "Place the next page on the glass to add another page (saved as sequentially numbered files), or tap Finish below."
        : "Place the next page (or flip the document) on the scanner glass to add another page, or tap Finish below."
      : "Review the scanned document pages before delivering.";

  return (
    <div className="flex h-[100dvh] w-[100dvw] flex-col overflow-hidden bg-kiosk-industrial-bezel text-zinc-100">
      <header className="flex shrink-0 items-center justify-between gap-2 border-b border-kiosk-industrial-border bg-kiosk-industrial-navy px-3 py-2.5 md:px-6">
        <div className="flex items-center gap-3">
          <button
            type="button"
            disabled={ctrl.hardwareBusy}
            onClick={() => {
              if (ctrl.pendingScanId) {
                void ctrl.cancelOperation();
              }
              nav("/scan");
            }}
            className="flex h-11 items-center justify-center rounded-xl border border-kiosk-industrial-border bg-kiosk-industrial-slate px-3.5 text-sm font-black uppercase tracking-wider text-zinc-100 disabled:opacity-40 active:scale-95"
          >
            ← Back
          </button>
          <div>
            <p className="text-[10px] font-semibold uppercase tracking-wider text-zinc-500">
              {destMeta.subtitle}
            </p>
            <h1 className="text-lg font-black uppercase tracking-wide text-zinc-100 md:text-2xl">
              {destMeta.title}
            </h1>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {ctrl.stage === "idle" && (
            <button
              type="button"
              disabled={ctrl.hardwareBusy}
              onClick={() => void ctrl.runScanPageStep(null, true)}
              className="flex h-11 items-center gap-1.5 rounded-xl border border-amber-500/40 bg-amber-500/15 px-3.5 text-xs font-black uppercase tracking-wider text-amber-300 disabled:opacity-40 active:scale-95"
              title="Scan and preview before saving or sending"
            >
              🔍 Preview
            </button>
          )}
        </div>
      </header>

      <main className="mx-auto flex min-h-0 w-full max-w-5xl flex-1 flex-col justify-between gap-3 overflow-y-auto p-3 md:p-5">
        {(ctrl.stage === "scanning" || ctrl.stage === "delivering") && (
          <div className="my-auto flex w-full max-w-xl flex-col items-center gap-6 self-center px-2">
            <div className="w-full">
              <ProgressBar
                label={
                  ctrl.stage === "delivering"
                    ? destination === "email"
                      ? "Sending Email…"
                      : destination === "usb"
                        ? "Saving to USB Flash Drive…"
                        : "Saving to Archive…"
                    : ctrl.isMultiStepFlatbed
                      ? `Scanning Page ${ctrl.scannedPages + 1} from Flatbed…`
                      : "Scanning Document…"
                }
                variant="scan"
              />
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
            headerBadge={`${destMeta.title} Preview`}
            headingText={`${ctrl.scannedPages} ${ctrl.scannedPages === 1 ? "Page" : "Pages"} Scanned`}
            descriptionText={previewDescription}
            showAddPageButton={ctrl.source === "flatbed"}
            finishLabel={destMeta.finishLabel}
            cancelLabel="Cancel Scan"
            onRotate={() => void ctrl.rotateCurrentPreviewPage()}
            onPrevPage={() => ctrl.setPreviewPage((p) => Math.max(0, p - 1))}
            onNextPage={() =>
              ctrl.setPreviewPage((p) => Math.min(ctrl.scannedPages - 1, p + 1))
            }
            onAddPage={() => void ctrl.runScanPageStep(ctrl.pendingScanId, true)}
            onFinish={() => void ctrl.runDeliverStep(ctrl.pendingScanId)}
            onCancel={() => void ctrl.cancelOperation()}
          />
        )}

        {ctrl.stage === "idle" && (
          <>
            <ScanDestinationHeader
              destination={destination}
              hardwareBusy={ctrl.hardwareBusy}
              outputFormat={ctrl.outputFormat}
              email={ctrl.email}
              emailSubject={ctrl.emailSubject}
              emailBody={ctrl.emailBody}
              fileName={ctrl.fileName}
              usbDrives={ctrl.usbDrives}
              selectedUsbDevice={ctrl.selectedUsbDevice}
              loadingDrives={ctrl.loadingDrives}
              onEmailChange={ctrl.setEmail}
              onEmailSubjectChange={ctrl.setEmailSubject}
              onEmailBodyChange={ctrl.setEmailBody}
              onFileNameChange={ctrl.setFileName}
              onRefreshUsbDrives={() => void ctrl.fetchUsbDrives()}
              onSelectUsbDevice={ctrl.setSelectedUsbDevice}
            />

            <ScanSettingsGrid
              source={ctrl.source}
              scanDuplex={ctrl.scanDuplex}
              color={ctrl.color}
              outputFormat={ctrl.outputFormat}
              quality={ctrl.quality}
              removeBlankPages={ctrl.removeBlankPages}
              hardwareBusy={ctrl.hardwareBusy}
              onToggleSource={() =>
                ctrl.setSource((s) => (s === "flatbed" ? "adf" : "flatbed"))
              }
              onToggleDuplex={() => ctrl.setScanDuplex((d) => !d)}
              onToggleColor={() => ctrl.setColor((c) => !c)}
              onCycleFormat={ctrl.cycleFormat}
              onCycleQuality={ctrl.cycleQuality}
              onToggleRemoveBlankPages={() => ctrl.setRemoveBlankPages((v) => !v)}
            />

            <div className="flex shrink-0 items-center justify-end gap-3 border-t border-kiosk-industrial-border pt-2.5">
              <KioskButton
                variant="primary"
                className="min-h-[4rem] w-full text-xl font-black uppercase tracking-wider"
                disabled={ctrl.hardwareBusy}
                onClick={() => void ctrl.runScanPageStep(null, false)}
              >
                {ctrl.source === "flatbed"
                  ? `Scan Page 1 (${destMeta.title})`
                  : destMeta.actionLabel}
              </KioskButton>
            </div>
          </>
        )}
      </main>

      <StatusModal
        open={ctrl.modal !== null}
        title={ctrl.modal?.title ?? ""}
        message={ctrl.modal?.detail ?? ""}
        onClose={() => ctrl.setModal(null)}
      />
    </div>
  );
}
