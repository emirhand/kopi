import type { ButtonHTMLAttributes, ReactNode } from "react";

type Variant = "primary" | "secondary" | "ghost" | "danger" | "industrial" | "industrialMuted";

const variants: Record<Variant, string> = {
  primary:
    "bg-kiosk-accent text-white border-kiosk-industrial-border active:bg-blue-600",
  secondary:
    "bg-kiosk-panel text-kiosk-text border-white/25 active:bg-zinc-800",
  ghost: "bg-transparent text-kiosk-muted border-white/15 active:bg-white/5",
  danger:
    "bg-kiosk-danger text-white border-red-700/50 active:bg-red-600",
  industrial:
    "bg-kiosk-industrial-slate text-zinc-100 border-kiosk-industrial-border shadow-[inset_0_1px_0_rgba(255,255,255,0.06)] active:bg-kiosk-industrial-navy",
  industrialMuted:
    "bg-kiosk-industrial-navy/80 text-zinc-400 border-kiosk-industrial-border/60 opacity-70 active:opacity-90 active:bg-kiosk-industrial-navy",
};

export type KioskButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: Variant;
  children: ReactNode;
  /** Large icon shown above label when layout is "tile" */
  icon?: ReactNode;
  /** "tile" = industrial square panel with icon + label; "default" = legacy row layout */
  layout?: "default" | "tile";
  /** Small badge e.g. "Coming soon" */
  badge?: ReactNode;
  /** Selected / active state for tile grids (e.g. Copy settings) */
  tileActive?: boolean;
};

export function KioskButton({
  variant = "primary",
  className = "",
  children,
  icon,
  layout = "default",
  badge,
  tileActive,
  ...rest
}: KioskButtonProps) {
  const industrialShadow = "shadow-[0_1px_2px_rgba(0,0,0,0.45)]";
  const tileActiveRing =
    tileActive === true
      ? "ring-2 ring-emerald-500 shadow-[0_0_16px_rgba(16,185,129,0.35)] border-emerald-500/70"
      : "";

  if (layout === "tile") {
    return (
      <button
        type="button"
        className={`
          relative flex aspect-square w-full max-h-full flex-col items-center justify-center gap-2
          rounded-3xl border-2 px-3 py-4 font-kiosk transition-[transform,background-color,opacity,box-shadow]
          select-none active:scale-95 disabled:pointer-events-none disabled:opacity-40
          [&_svg]:shrink-0
          ${industrialShadow}
          ${variants[variant]}
          ${tileActiveRing}
          ${className}
        `}
        {...rest}
      >
        {badge != null && (
          <span className="absolute right-2 top-2 rounded-md border border-white/15 bg-black/35 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-zinc-300">
            {badge}
          </span>
        )}
        {icon != null && <span className="flex items-center justify-center [&_svg]:h-14 [&_svg]:w-14 md:[&_svg]:h-16 md:[&_svg]:w-16">{icon}</span>}
        <span className="text-center text-sm font-black uppercase leading-tight tracking-wide md:text-base">
          {children}
        </span>
      </button>
    );
  }

  return (
    <button
      type="button"
      className={`
        rounded-2xl font-kiosk font-semibold tracking-wide transition-[transform,background-color]
        select-none active:scale-95 disabled:pointer-events-none disabled:opacity-40
        min-h-[4.5rem] border-2 px-6 text-xl md:text-2xl
        ${industrialShadow}
        ${variants[variant]}
        ${className}
      `}
      {...rest}
    >
      {children}
    </button>
  );
}
