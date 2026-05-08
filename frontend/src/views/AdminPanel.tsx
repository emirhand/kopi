import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { apiUrl, parseErrorDetail } from "../api";
import { KioskButton } from "../components/KioskButton";
import { StatusModal } from "../components/StatusModal";
import { clearAdminSession, getAdminPassword } from "./AdminLogin";

type Smtp = {
  host: string;
  port: number;
  user: string;
  password: string;
  from_email: string;
  tls: boolean;
};

type HardwareOptions = {
  scanners: string[];
  printers: string[];
};

const emptySmtp: Smtp = {
  host: "",
  port: 587,
  user: "",
  password: "",
  from_email: "",
  tls: true,
};

export function AdminPanel() {
  const nav = useNavigate();
  const [smtp, setSmtp] = useState<Smtp>(emptySmtp);
  const [loaded, setLoaded] = useState(false);
  const [busy, setBusy] = useState(false);
  const [scannerDevice, setScannerDevice] = useState("");
  const [printerDevice, setPrinterDevice] = useState("");
  const [usbRootsText, setUsbRootsText] = useState("/media\n/run/media\n/Volumes");
  const [idScanOcr, setIdScanOcr] = useState(false);
  const [hardwareOptions, setHardwareOptions] = useState<HardwareOptions>({ scanners: [], printers: [] });
  const [modal, setModal] = useState<{ title: string; message: string; variant: "info" | "error" } | null>(
    null,
  );

  useEffect(() => {
    const pw = getAdminPassword();
    if (!pw) {
      nav("/admin", { replace: true });
      return;
    }

    (async () => {
      try {
        const res = await fetch(apiUrl("/api/admin/settings"), {
          headers: { "X-Admin-Password": pw },
        });
        if (res.status === 401 || res.status === 403) {
          clearAdminSession();
          nav("/admin", { replace: true });
          return;
        }
        if (!res.ok) {
          setModal({ title: "Settings", message: await parseErrorDetail(res), variant: "error" });
          return;
        }
        const data = await res.json();
        setSmtp({ ...emptySmtp, ...data.smtp });
        setScannerDevice(typeof data.scanner_device === "string" ? data.scanner_device : "");
        setPrinterDevice(typeof data.printer_device === "string" ? data.printer_device : "");
        setUsbRootsText(Array.isArray(data.usb_roots) && data.usb_roots.length > 0 ? data.usb_roots.join("\n") : "/media\n/run/media\n/Volumes");
        setIdScanOcr(Boolean(data.id_scan_ocr));
        setHardwareOptions({
          scanners: Array.isArray(data?.hardware_options?.scanners) ? data.hardware_options.scanners : [],
          printers: Array.isArray(data?.hardware_options?.printers) ? data.hardware_options.printers : [],
        });
      } catch (e) {
        setModal({
          title: "Settings",
          message: e instanceof Error ? e.message : "Network error",
          variant: "error",
        });
      } finally {
        setLoaded(true);
      }
    })();
  }, [nav]);

  async function save() {
    const pw = getAdminPassword();
    if (!pw) {
      nav("/admin", { replace: true });
      return;
    }
    setBusy(true);
    try {
      const res = await fetch(apiUrl("/api/admin/settings"), {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
          "X-Admin-Password": pw,
        },
        body: JSON.stringify({
          smtp,
          scanner_device: scannerDevice,
          printer_device: printerDevice,
          usb_roots: usbRootsText
            .split("\n")
            .map((x) => x.trim())
            .filter(Boolean),
          id_scan_ocr: idScanOcr,
        }),
      });
      if (!res.ok) {
        setModal({ title: "Save", message: await parseErrorDetail(res), variant: "error" });
        return;
      }
      setModal({ title: "Save", message: "Settings saved.", variant: "info" });
    } catch (e) {
      setModal({
        title: "Save",
        message: e instanceof Error ? e.message : "Network error",
        variant: "error",
      });
    } finally {
      setBusy(false);
    }
  }

  function logout() {
    clearAdminSession();
    nav("/");
  }

  if (!loaded) {
    return (
      <div className="h-full flex items-center justify-center bg-kiosk-bg text-kiosk-muted text-xl">
        Loading…
      </div>
    );
  }

  const field =
    "w-full rounded-2xl border-2 border-white/20 bg-kiosk-panel px-4 py-3 text-lg text-kiosk-text outline-none focus:border-kiosk-accent";

  return (
    <div className="h-full flex flex-col bg-kiosk-bg p-4 gap-3 overflow-hidden">
      <div className="shrink-0 flex items-center gap-2">
        <KioskButton variant="ghost" className="min-h-[3rem] px-4 text-base" onClick={() => nav("/")}>
          Home
        </KioskButton>
        <h2 className="text-xl font-bold flex-1">Admin Settings</h2>
        <KioskButton variant="secondary" className="min-h-[3rem] px-4 text-base" onClick={logout}>
          Log out
        </KioskButton>
      </div>

      <div className="flex-1 min-h-0 grid grid-cols-1 gap-2 content-start">
        <h3 className="text-sm uppercase tracking-wide text-kiosk-muted">Hardware</h3>
        <label className="text-sm text-kiosk-muted">
          Scanner device
          <select
            className={`${field} mt-1`}
            value={scannerDevice}
            onChange={(e) => setScannerDevice(e.target.value)}
          >
            <option value="">Auto/default scanner</option>
            {scannerDevice && !hardwareOptions.scanners.includes(scannerDevice) && (
              <option value={scannerDevice}>{scannerDevice}</option>
            )}
            {hardwareOptions.scanners.map((dev) => (
              <option key={dev} value={dev}>
                {dev}
              </option>
            ))}
          </select>
        </label>
        <label className="text-sm text-kiosk-muted">
          Printer queue
          <select
            className={`${field} mt-1`}
            value={printerDevice}
            onChange={(e) => setPrinterDevice(e.target.value)}
          >
            <option value="">Default printer</option>
            {printerDevice && !hardwareOptions.printers.includes(printerDevice) && (
              <option value={printerDevice}>{printerDevice}</option>
            )}
            {hardwareOptions.printers.map((queue) => (
              <option key={queue} value={queue}>
                {queue}
              </option>
            ))}
          </select>
        </label>
        <label className="text-sm text-kiosk-muted">
          USB roots (one per line)
          <textarea
            className={`${field} mt-1 min-h-[6rem]`}
            value={usbRootsText}
            onChange={(e) => setUsbRootsText(e.target.value)}
            spellCheck={false}
          />
        </label>
        <h3 className="text-sm uppercase tracking-wide text-kiosk-muted mt-1">ID scan</h3>
        <KioskButton
          variant={idScanOcr ? "primary" : "secondary"}
          className="w-full text-lg min-h-[3.5rem]"
          onClick={() => setIdScanOcr((v) => !v)}
        >
          ID Scan OCR (ocrmypdf): {idScanOcr ? "On" : "Off"}
        </KioskButton>
        <h3 className="text-sm uppercase tracking-wide text-kiosk-muted mt-1">SMTP</h3>
        <label className="text-sm text-kiosk-muted">
          Server
          <input
            className={`${field} mt-1`}
            value={smtp.host}
            onChange={(e) => setSmtp((s) => ({ ...s, host: e.target.value }))}
            autoComplete="off"
          />
        </label>
        <label className="text-sm text-kiosk-muted">
          Port
          <input
            className={`${field} mt-1`}
            type="number"
            inputMode="numeric"
            value={smtp.port}
            onChange={(e) => setSmtp((s) => ({ ...s, port: Number(e.target.value) || 0 }))}
          />
        </label>
        <label className="text-sm text-kiosk-muted">
          User
          <input
            className={`${field} mt-1`}
            value={smtp.user}
            onChange={(e) => setSmtp((s) => ({ ...s, user: e.target.value }))}
            autoComplete="username"
          />
        </label>
        <label className="text-sm text-kiosk-muted">
          Password
          <input
            className={`${field} mt-1`}
            type="password"
            value={smtp.password}
            onChange={(e) => setSmtp((s) => ({ ...s, password: e.target.value }))}
            autoComplete="new-password"
          />
        </label>
        <label className="text-sm text-kiosk-muted">
          From
          <input
            className={`${field} mt-1`}
            type="email"
            value={smtp.from_email}
            onChange={(e) => setSmtp((s) => ({ ...s, from_email: e.target.value }))}
          />
        </label>
        <KioskButton
          variant={smtp.tls ? "primary" : "secondary"}
          className="w-full text-lg min-h-[3.5rem]"
          onClick={() => setSmtp((s) => ({ ...s, tls: !s.tls }))}
        >
          TLS: {smtp.tls ? "On" : "Off"}
        </KioskButton>
      </div>

      <KioskButton variant="primary" className="shrink-0 w-full text-2xl" disabled={busy} onClick={save}>
        {busy ? "Saving…" : "Save"}
      </KioskButton>

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
