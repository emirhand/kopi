import { KioskButton } from "./KioskButton";

export type KeypadProps = {
  onDigit: (d: string) => void;
  onBackspace: () => void;
  onClear: () => void;
  className?: string;
};

const keys = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "C", "0", "⌫"];

export function Keypad({ onDigit, onBackspace, onClear, className = "" }: KeypadProps) {
  return (
    <div
      className={`grid grid-cols-3 gap-3 ${className}`}
      aria-label="Numeric keypad"
    >
      {keys.map((k) => (
        <KioskButton
          key={k}
          variant="secondary"
          className="min-h-[4rem] text-3xl font-bold py-4"
          onClick={() => {
            if (k === "⌫") onBackspace();
            else if (k === "C") onClear();
            else onDigit(k);
          }}
        >
          {k}
        </KioskButton>
      ))}
    </div>
  );
}
