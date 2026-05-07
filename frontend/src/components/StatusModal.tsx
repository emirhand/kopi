import { KioskButton } from "./KioskButton";

export type StatusModalProps = {
  open: boolean;
  title: string;
  message: string;
  variant?: "info" | "error";
  onClose: () => void;
};

export function StatusModal({
  open,
  title,
  message,
  variant = "info",
  onClose,
}: StatusModalProps) {
  if (!open) return null;

  const accent =
    variant === "error"
      ? "border-kiosk-danger ring-2 ring-kiosk-danger/40"
      : "border-kiosk-accent ring-2 ring-kiosk-accent/30";

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="status-title"
    >
      <div
        className={`w-full max-w-lg rounded-3xl border-4 bg-kiosk-panel p-6 ${accent}`}
      >
        <h2 id="status-title" className="text-2xl font-bold text-kiosk-text mb-3">
          {title}
        </h2>
        <p className="text-lg text-kiosk-muted leading-snug mb-6 whitespace-pre-wrap">
          {message}
        </p>
        <KioskButton variant="primary" className="w-full" onClick={onClose}>
          OK
        </KioskButton>
      </div>
    </div>
  );
}
