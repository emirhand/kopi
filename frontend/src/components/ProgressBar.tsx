export type ProgressBarProps = {
  label: string;
  variant?: "scan" | "print";
};

const variantClass: Record<NonNullable<ProgressBarProps["variant"]>, string> = {
  scan: "from-kiosk-accent via-kiosk-accent2 to-kiosk-accent",
  print: "from-kiosk-accent2 via-kiosk-accent to-kiosk-accent2",
};

export function ProgressBar({ label, variant = "scan" }: ProgressBarProps) {
  const grad = variantClass[variant];
  return (
    <div className="w-full space-y-3">
      <p className="text-center text-xl md:text-2xl font-bold text-kiosk-text tracking-wide">
        {label}
      </p>
      <div
        className="relative h-4 w-full overflow-hidden rounded-full border-2 border-white/20 bg-black/40"
        role="progressbar"
        aria-valuetext={label}
        aria-busy="true"
      >
        <div
          className={`pointer-events-none absolute inset-y-0 w-1/3 bg-gradient-to-r ${grad} opacity-90 animate-kopi-shimmer`}
        />
      </div>
    </div>
  );
}
