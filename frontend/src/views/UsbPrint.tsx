import { useNavigate } from "react-router-dom";
import { KioskButton } from "../components/KioskButton";
import { ProgressBar } from "../components/ProgressBar";
import { StatusModal } from "../components/StatusModal";
import { UsbFileBrowser } from "./usb-print/UsbFileBrowser";
import { UsbPrintPreviewAndOptions } from "./usb-print/UsbPrintPreviewAndOptions";
import { useUsbPrintController } from "./usb-print/useUsbPrintController";

export function UsbPrint() {
  const nav = useNavigate();
  const ctrl = useUsbPrintController();

  return (
    <div className="flex h-[100dvh] w-[100dvw] flex-col overflow-hidden bg-kiosk-industrial-bezel text-zinc-100">
      <header className="flex shrink-0 items-center justify-between gap-2 border-b border-kiosk-industrial-border bg-kiosk-industrial-navy px-3 py-2.5 md:px-6">
        <div className="flex items-center gap-3">
          <button
            type="button"
            disabled={ctrl.printing}
            onClick={() => {
              if (ctrl.selectedFile) {
                ctrl.setSelectedFile(null);
              } else {
                nav("/");
              }
            }}
            className="flex h-11 items-center justify-center rounded-xl border border-kiosk-industrial-border bg-kiosk-industrial-slate px-3.5 text-sm font-black uppercase tracking-wider text-zinc-100 disabled:opacity-40 active:scale-95"
          >
            ← {ctrl.selectedFile ? "Files" : "Back"}
          </button>
          <div>
            <p className="text-[10px] font-semibold uppercase tracking-wider text-zinc-500">
              HP 9010 USB Print
            </p>
            <h1 className="text-lg font-black uppercase tracking-wide text-zinc-100 md:text-2xl">
              {ctrl.selectedFile ? ctrl.selectedFile.name : "Print from USB"}
            </h1>
          </div>
        </div>

        {ctrl.selectedFile && (
          <div className="flex items-center gap-1.5 rounded-xl border border-kiosk-industrial-border bg-kiosk-industrial-slate/70 px-2.5 py-1.5">
            <span className="mr-1 hidden text-xs font-semibold uppercase tracking-wider text-zinc-400 sm:inline">
              Copies
            </span>
            <button
              type="button"
              disabled={ctrl.printing || ctrl.copies <= 1}
              onClick={() => ctrl.setCopies((c) => Math.max(1, c - 1))}
              className="flex h-9 w-9 items-center justify-center rounded-lg border border-kiosk-industrial-border bg-kiosk-industrial-navy text-xl font-bold text-zinc-100 disabled:opacity-40 active:scale-95"
            >
              −
            </button>
            <span className="min-w-[2.5rem] text-center font-mono text-2xl font-black tabular-nums text-emerald-400">
              {ctrl.copies}
            </span>
            <button
              type="button"
              disabled={ctrl.printing || ctrl.copies >= 99}
              onClick={() => ctrl.setCopies((c) => Math.min(99, c + 1))}
              className="flex h-9 w-9 items-center justify-center rounded-lg border border-kiosk-industrial-border bg-kiosk-industrial-navy text-xl font-bold text-zinc-100 disabled:opacity-40 active:scale-95"
            >
              +
            </button>
          </div>
        )}
      </header>

      <main className="mx-auto flex min-h-0 w-full max-w-5xl flex-1 flex-col gap-3 overflow-y-auto p-3 md:p-5">
        {ctrl.printing && (
          <div className="my-auto flex w-full max-w-xl flex-col items-center gap-6 self-center px-2">
            <div className="w-full">
              <ProgressBar
                label={`Printing ${ctrl.selectedFile?.name ?? "document"} (${ctrl.copies} ${ctrl.copies === 1 ? "copy" : "copies"})…`}
                variant="print"
              />
            </div>
            <KioskButton
              variant="industrial"
              className="min-h-[4rem] w-full max-w-xs border-2 border-red-500/70 bg-red-950/60 text-xl font-black uppercase tracking-wider text-red-200 ring-2 ring-red-500/30"
              disabled={ctrl.cancelling}
              onClick={() => void ctrl.cancelPrint()}
            >
              {ctrl.cancelling ? "Stopping…" : "Stop / Cancel"}
            </KioskButton>
          </div>
        )}

        {!ctrl.printing && !ctrl.selectedFile && (
          <UsbFileBrowser
            usbDrives={ctrl.usbDrives}
            selectedDevice={ctrl.selectedDevice}
            loadingDrives={ctrl.loadingDrives}
            subpath={ctrl.subpath}
            entries={ctrl.entries}
            loadingFiles={ctrl.loadingFiles}
            onRefreshDrives={() => void ctrl.fetchDrives()}
            onSelectDevice={ctrl.setSelectedDevice}
            onNavigateUp={ctrl.navigateUpFolder}
            onOpenFolder={ctrl.openFolder}
            onSelectFile={ctrl.selectPrintableFile}
          />
        )}

        {!ctrl.printing && ctrl.selectedFile && (
          <UsbPrintPreviewAndOptions
            selectedFile={ctrl.selectedFile}
            previewPage={ctrl.previewPage}
            previewUrl={ctrl.buildPreviewUrl(ctrl.selectedFile, ctrl.previewPage)}
            copies={ctrl.copies}
            sidesMode={ctrl.sidesMode}
            color={ctrl.color}
            quality={ctrl.quality}
            paperSize={ctrl.paperSize}
            fitToPage={ctrl.fitToPage}
            collate={ctrl.collate}
            onPrevPage={() => ctrl.setPreviewPage((p) => Math.max(0, p - 1))}
            onNextPage={() =>
              ctrl.setPreviewPage((p) => Math.min(ctrl.selectedFile!.pages - 1, p + 1))
            }
            onCycleSides={ctrl.cycleSides}
            onToggleColor={() => ctrl.setColor((c) => !c)}
            onCycleQuality={ctrl.cycleQuality}
            onCyclePaperSize={ctrl.cyclePaperSize}
            onToggleFitToPage={() => ctrl.setFitToPage((f) => !f)}
            onToggleCollate={() => ctrl.setCollate((c) => !c)}
            onStartPrint={() => void ctrl.startPrint()}
            onChooseDifferentFile={() => ctrl.setSelectedFile(null)}
          />
        )}
      </main>

      <StatusModal
        open={ctrl.modal !== null}
        title={ctrl.modal?.title ?? ""}
        message={ctrl.modal?.message ?? ""}
        variant={ctrl.modal?.variant}
        onClose={() => ctrl.setModal(null)}
      />
    </div>
  );
}
