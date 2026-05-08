import { useNavigate } from "react-router-dom";
import { KioskButton } from "../components/KioskButton";

export function Home() {
  const nav = useNavigate();

  return (
    <div className="h-[100dvh] w-[100dvw] flex flex-col bg-kiosk-bg overflow-hidden">
      <header className="shrink-0 px-4 pt-4 pb-2 flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h1 className="text-2xl md:text-4xl font-black tracking-tight text-kiosk-text leading-tight">
            Smart Copier
          </h1>
          <p className="mt-1 text-sm md:text-base text-kiosk-muted">Tap a task to begin</p>
        </div>
        <button
          type="button"
          onClick={() => nav("/admin")}
          className="shrink-0 rounded-2xl border-2 border-white/15 bg-kiosk-panel px-4 py-3 text-sm md:text-base font-semibold text-kiosk-muted active:scale-[0.98] min-h-[3rem] min-w-[6rem]"
        >
          Admin
        </button>
      </header>

      <main className="flex-1 min-h-0 p-3 md:p-4 flex flex-col gap-3 md:gap-4">
        <KioskButton
          variant="primary"
          className="flex-1 w-full min-h-0 text-4xl sm:text-5xl md:text-6xl font-black uppercase ring-2 ring-white/10 active:scale-[0.99]"
          onClick={() => nav("/copy")}
        >
          Copy
        </KioskButton>
        <KioskButton
          variant="secondary"
          className="flex-1 w-full min-h-0 text-4xl sm:text-5xl md:text-6xl font-black uppercase border-kiosk-accent2/50 ring-2 ring-kiosk-accent2/20 active:scale-[0.99]"
          onClick={() => nav("/scan")}
        >
          Scan
        </KioskButton>
      </main>
    </div>
  );
}
