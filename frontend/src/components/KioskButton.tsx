import type { ButtonHTMLAttributes, ReactNode } from "react";

type Variant = "primary" | "secondary" | "ghost" | "danger";

const variants: Record<Variant, string> = {
  primary:
    "bg-kiosk-accent text-white border-2 border-white/20 shadow-lg shadow-black/40 active:scale-[0.98]",
  secondary:
    "bg-kiosk-panel text-kiosk-text border-2 border-white/25 shadow-md active:scale-[0.98]",
  ghost: "bg-transparent text-kiosk-muted border-2 border-white/15 active:scale-[0.98]",
  danger:
    "bg-kiosk-danger text-white border-2 border-white/20 shadow-lg active:scale-[0.98]",
};

export type KioskButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: Variant;
  children: ReactNode;
};

export function KioskButton({
  variant = "primary",
  className = "",
  children,
  ...rest
}: KioskButtonProps) {
  return (
    <button
      type="button"
      className={`rounded-2xl font-kiosk font-semibold tracking-wide transition-transform select-none min-h-[4.5rem] px-6 text-xl md:text-2xl disabled:opacity-40 disabled:pointer-events-none ${variants[variant]} ${className}`}
      {...rest}
    >
      {children}
    </button>
  );
}
