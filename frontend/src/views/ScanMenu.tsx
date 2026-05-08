import type { CSSProperties } from "react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { apiUrl, parseErrorDetail } from "../api";
import { IconArchive, IconMail, IconUsb } from "../components/IndustrialIcons";
import { KioskButton } from "../components/KioskButton";
import { StatusModal } from "../components/StatusModal";
import { KOPI_USB_MOUNT_STORAGE_KEY } from "../usbStorage";

const PRO_GRID_STYLE: CSSProperties = {
  width: "min(92vw, 42rem)",
};

export function ScanMenu() {
  const nav = useNavigate();
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState<null | "email" | "usb" | "archive">(null);
  const [duplex, setDuplex] = useState(false);
  const [scanColor, setScanColor] = useState(true);
  const [resolution, setResolution] = useState<"standard" | "high">("standard");
  const [outputFormat, setOutputFormat] = useState<"pdf" | "jpg">("pdf");
  const [removeBlankPages, setRemoveBlankPages] = useState(false);
  const [modal, setModal] = useState<{ title: string; message: string; variant: "info" | "error" } | null>(
    null,
  );

  const hardwareBusy = busy !== null;

  const scanOptionsBody = () => ({
    duplex,
    color: scanColor,
    resolution,
    output_format: outputFormat,
    remove_blank_pages: removeBlankPages && outputFormat === "pdf",
  });

  async function scanEmail() {
    if (!email.trim()) {
      setModal({ title: "Scan to Email", message: "Enter an email address.", variant: "error" });
      return;
    }
    setBusy("email");
    try {
      const res = await fetch(apiUrl("/api/scan/email"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          recipient: email.trim(),
          ...scanOptionsBody(),
        }),
      });
      if (!res.ok) {
        const msg = await parseErrorDetail(res);
        setModal({ title: "Scan to Email", message: msg, variant: "error" });
        return;
      }
      setModal({ title: "Scan to Email", message: "Scan emailed.", variant: "info" });
    } catch (e) {
      setModal({
        title: "Scan to Email",
        message: e instanceof Error ? e.message : "Network error",
        variant: "error",
      });
    } finally {
      setBusy(null);
    }
  }

  async function scanUsb() {
    setBusy("usb");
    try {
      let mountPath: string | null = null;
      try {
        const raw = sessionStorage.getItem(KOPI_USB_MOUNT_STORAGE_KEY);
        mountPath = raw && raw.trim() ? raw.trim() : null;
      } catch {
        mountPath = null;
      }
      const res = await fetch(apiUrl("/api/scan/usb"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          mount_path: mountPath,
          ...scanOptionsBody(),
        }),
      });
      if (!res.ok) {
        const msg = await parseErrorDetail(res);
        setModal({ title: "Scan to USB", message: msg, variant: "error" });
        return;
      }
      const data = await res.json();
      setModal({ title: "Scan to USB", message: data.message ?? "Saved.", variant: "info" });
    } catch (e) {
      setModal({
        title: "Scan to USB",
        message: e instanceof Error ? e.message : "Network error",
        variant: "error",
      });
    } finally {
      setBusy(null);
    }
  }

  async function scanArchive() {
    setBusy("archive");
    try {
      const res = await fetch(apiUrl("/api/scan/archive"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(scanOptionsBody()),
      });
      if (!res.ok) {
        const msg = await parseErrorDetail(res);
        setModal({ title: "Archive", message: msg, variant: "error" });
        return;
      }
      const data = await res.json();
      setModal({ title: "Archive", message: data.message ?? "Saved.", variant: "info" });
    } catch (e) {
      setModal({
        title: "Archive",
        message: e instanceof Error ? e.message : "Network error",
        variant: "error",
      });
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="flex h-[100dvh] min-h-0 w-[100dvw] flex-col overflow-hidden bg-kiosk-industrial-bezel text-zinc-100">
      <header className="shrink-0 px-4 pt-3 text-center">
        <p className="text-[10px] font-semibold uppercase tracking-wider text-zinc-500">Capture</p>
        <h1 className="text-xl font-black uppercase tracking-wide md:text-2xl">Scan</h1>
      </header>

      <div className="shrink-0 px-4 pb-2">
        <label className="block">
          <span className="sr-only">Email</span>
          <input
            type="email"
            inputMode="email"
            autoComplete="email"
            placeholder="recipient@example.com"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            disabled={hardwareBusy}
            className="w-full rounded-2xl border-2 border-kiosk-industrial-border bg-kiosk-industrial-navy px-4 py-3 text-lg text-zinc-100 placeholder:text-zinc-500 outline-none focus:border-emerald-500/60"
          />
        </label>
      </div>

      <main className="flex min-h-0 flex-1 flex-col items-center gap-4 overflow-y-auto px-3 pb-4 md:px-6">
        <div
          className="grid min-h-0 shrink-0 grid-cols-3 grid-rows-1 gap-3 md:gap-4"
          style={{
            width: "min(92vw, calc((100dvh - 14rem) * 3 / 2))",
            height: "min(28vw, 12rem)",
            maxHeight: "min(28dvh, 14rem)",
          }}
        >
          <KioskButton
            layout="tile"
            variant="industrial"
            icon={<IconMail className="text-sky-400" />}
            className="min-h-0 min-w-0"
            disabled={hardwareBusy}
            onClick={scanEmail}
          >
            {busy === "email" ? "…" : "Email"}
          </KioskButton>
          <KioskButton
            layout="tile"
            variant="industrial"
            icon={<IconUsb className="text-amber-400" />}
            className="min-h-0 min-w-0"
            disabled={hardwareBusy}
            onClick={scanUsb}
          >
            {busy === "usb" ? "…" : "USB"}
          </KioskButton>
          <KioskButton
            layout="tile"
            variant="industrial"
            icon={<IconArchive className="text-violet-400" />}
            className="min-h-0 min-w-0"
            disabled={hardwareBusy}
            onClick={scanArchive}
          >
            {busy === "archive" ? "…" : "Archive"}
          </KioskButton>
        </div>

        <p className="text-center text-[10px] font-semibold uppercase tracking-wider text-zinc-500">Pro</p>

        <div className="mx-auto grid w-full max-w-lg grid-cols-2 gap-3 md:gap-4" style={PRO_GRID_STYLE}>
          <KioskButton
            layout="tile"
            variant="industrial"
            tileActive={outputFormat === "pdf"}
            className="min-h-0 min-w-0"
            disabled={hardwareBusy}
            onClick={() => setOutputFormat("pdf")}
          >
            PDF
          </KioskButton>
          <KioskButton
            layout="tile"
            variant="industrial"
            tileActive={outputFormat === "jpg"}
            className="min-h-0 min-w-0"
            disabled={hardwareBusy}
            onClick={() => setOutputFormat("jpg")}
          >
            JPG
          </KioskButton>
          <KioskButton
            layout="tile"
            variant="industrial"
            tileActive={resolution === "standard"}
            className="min-h-0 min-w-0"
            disabled={hardwareBusy}
            onClick={() => setResolution("standard")}
          >
            Standard
            <span className="block text-[10px] font-normal normal-case text-zinc-500">150 dpi</span>
          </KioskButton>
          <KioskButton
            layout="tile"
            variant="industrial"
            tileActive={resolution === "high"}
            className="min-h-0 min-w-0"
            disabled={hardwareBusy}
            onClick={() => setResolution("high")}
          >
            High
            <span className="block text-[10px] font-normal normal-case text-zinc-500">300 dpi</span>
          </KioskButton>
          <KioskButton
            layout="tile"
            variant="industrial"
            tileActive={scanColor}
            className="min-h-0 min-w-0"
            disabled={hardwareBusy}
            onClick={() => setScanColor(true)}
          >
            Color
          </KioskButton>
          <KioskButton
            layout="tile"
            variant="industrial"
            tileActive={!scanColor}
            className="min-h-0 min-w-0"
            disabled={hardwareBusy}
            onClick={() => setScanColor(false)}
          >
            B&amp;W
          </KioskButton>
          <KioskButton
            layout="tile"
            variant="industrial"
            tileActive={removeBlankPages}
            className="min-h-0 min-w-0"
            disabled={hardwareBusy || outputFormat !== "pdf"}
            onClick={() => setRemoveBlankPages((v) => !v)}
          >
            Remove blanks
          </KioskButton>
          <KioskButton
            layout="tile"
            variant="industrial"
            tileActive={duplex}
            className="min-h-0 min-w-0"
            disabled={hardwareBusy}
            onClick={() => setDuplex((v) => !v)}
          >
            Duplex
          </KioskButton>
        </div>

        <div className="mt-auto grid w-full shrink-0 grid-cols-3 gap-3 pb-2 pt-4 md:gap-4" style={{
          width: "min(92vw, calc((100dvh - 12rem) * 3 / 2))",
          marginLeft: "auto",
          marginRight: "auto",
        }}>
          <KioskButton
            layout="tile"
            variant="industrialMuted"
            className="col-span-1 min-h-0 min-w-0"
            style={{ aspectRatio: "1", maxHeight: "6rem" }}
            disabled={hardwareBusy}
            onClick={() => nav("/")}
          >
            ← Back
          </KioskButton>
        </div>
      </main>

      <StatusModal
        open={!!modal}
        title={modal?.title ?? ""}
        message={modal?.message ?? ""}
        variant={modal?.variant}
        onClose={() => setModal(null)}
      />
    </div>
  );
}
