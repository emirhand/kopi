import { KioskButton } from "../../components/KioskButton";

interface CopiesKeypadModalProps {
  open: boolean;
  buffer: string;
  onChangeBuffer: (updater: (prev: string) => string) => void;
  onClose: () => void;
  onConfirm: () => void;
}

export function CopiesKeypadModal({
  open,
  buffer,
  onChangeBuffer,
  onClose,
  onConfirm,
}: CopiesKeypadModalProps) {
  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 p-4">
      <div className="w-full max-w-sm rounded-3xl border border-kiosk-industrial-border bg-kiosk-industrial-navy p-5 shadow-2xl">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-black uppercase tracking-wider text-zinc-100">
            Number of Copies (1–99)
          </h2>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg px-3 py-1 text-sm font-bold text-zinc-400 hover:text-zinc-100"
          >
            ✕
          </button>
        </div>
        <div className="my-3 rounded-xl border border-kiosk-industrial-border bg-black/40 py-2.5 text-center font-mono text-3xl font-black text-emerald-400">
          {buffer || "1"}
        </div>
        <div className="grid grid-cols-3 gap-2">
          {["1", "2", "3", "4", "5", "6", "7", "8", "9", "C", "0", "⌫"].map((key) => (
            <button
              key={key}
              type="button"
              onClick={() => {
                if (key === "C") {
                  onChangeBuffer(() => "");
                } else if (key === "⌫") {
                  onChangeBuffer((b) => b.slice(0, -1));
                } else {
                  onChangeBuffer((b) => {
                    const next = (b + key).replace(/^0+/, "");
                    return next.length <= 2 ? next : b;
                  });
                }
              }}
              className="flex h-12 items-center justify-center rounded-xl border border-kiosk-industrial-border bg-kiosk-industrial-slate text-xl font-bold text-zinc-100 active:scale-95"
            >
              {key}
            </button>
          ))}
        </div>
        <div className="mt-4 flex gap-2">
          <KioskButton
            variant="industrialMuted"
            className="min-h-[3.25rem] flex-1 text-base"
            onClick={onClose}
          >
            Cancel
          </KioskButton>
          <KioskButton
            variant="industrial"
            className="min-h-[3.25rem] flex-1 text-base ring-1 ring-emerald-500/40"
            onClick={onConfirm}
          >
            OK
          </KioskButton>
        </div>
      </div>
    </div>
  );
}
