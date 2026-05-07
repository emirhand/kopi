import { useNavigate } from "react-router-dom";
import { KioskButton } from "../components/KioskButton";

export function Home() {
  const nav = useNavigate();

  return (
    <div className="h-full flex flex-col bg-kiosk-bg">
      <header className="shrink-0 px-4 pt-4 pb-2 flex items-center justify-between">
        <h1 className="text-2xl md:text-3xl font-extrabold tracking-tight text-kiosk-text">
          Smart Copier
        </h1>
        <button
          type="button"
          onClick={() => nav("/admin")}
          className="text-sm text-kiosk-muted underline-offset-4 hover:underline px-2 py-3 min-w-[4rem]"
        >
          Admin
        </button>
      </header>

      <main className="flex-1 min-h-0 p-4 flex flex-col gap-4">
        <KioskButton
          variant="primary"
          className="flex-1 w-full text-4xl md:text-5xl font-black uppercase"
          onClick={() => nav("/copy")}
        >
          Copy
        </KioskButton>
        <KioskButton
          variant="secondary"
          className="flex-1 w-full text-4xl md:text-5xl font-black uppercase border-kiosk-accent2/50"
          onClick={() => nav("/scan")}
        >
          Scan
        </KioskButton>
      </main>
    </div>
  );
}
