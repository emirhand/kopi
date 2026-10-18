import { useState } from "react";
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
  const [copied, setCopied] = useState(false);

  if (!open) return null;

  const accent =
    variant === "error"
      ? "border-kiosk-danger ring-2 ring-kiosk-danger/40"
      : "border-kiosk-accent ring-2 ring-kiosk-accent/30";

  async function copyMessage() {
    try {
      await navigator.clipboard.writeText(message);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      /* fallback: user can still drag-select text */
    }
  }

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
        <h2 id="status-title" className="text-2xl font-bold text-kiosk-text mb-3 select-text">
          {title}
        </h2>
        <p className="text-lg text-kiosk-muted leading-snug mb-6 whitespace-pre-wrap select-text cursor-text rounded-xl bg-black/20 p-3">
          {message}
        </p>
        <div className="flex gap-3">
          {variant === "error" && (
            <KioskButton variant="secondary" className="flex-1" onClick={copyMessage}>
              {copied ? "Copied!" : "Copy Error"}
            </KioskButton>
          )}
          <KioskButton variant="primary" className="flex-1" onClick={onClose}>
            OK
          </KioskButton>
        </div>
      </div>
    </div>
  );
}

