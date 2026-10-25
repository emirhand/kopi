import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { apiUrl, notifyPairingStateChanged, parseErrorDetail } from "../api";
import { KioskButton } from "../components/KioskButton";
import { StatusModal } from "../components/StatusModal";
import { clearAdminSession, getAdminPassword, setAdminPassword } from "./AdminLogin";

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
  const [smtpPasswordSet, setSmtpPasswordSet] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [busy, setBusy] = useState(false);
  const [scannerDevice, setScannerDevice] = useState("");
  const [printerDevice, setPrinterDevice] = useState("");
  const [idScanOcr, setIdScanOcr] = useState(false);
  const [pairingPin, setPairingPin] = useState("");
  const [pairingPinSet, setPairingPinSet] = useState(false);
  const [newAdminPassword, setNewAdminPassword] = useState("");
  const [pairedDeviceId, setPairedDeviceId] = useState<string | null>(null);
  const [pairedDeviceLabel, setPairedDeviceLabel] = useState<string | null>(null);
  const [pairedAt, setPairedAt] = useState<string | null>(null);
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
        setSmtp({
          host: typeof data.smtp?.host === "string" ? data.smtp.host : "",
          port: typeof data.smtp?.port === "number" ? data.smtp.port : 587,
          user: typeof data.smtp?.user === "string" ? data.smtp.user : "",
          password: "",
          from_email: typeof data.smtp?.from_email === "string" ? data.smtp.from_email : "",
          tls: typeof data.smtp?.tls === "boolean" ? data.smtp.tls : true,
        });
        setSmtpPasswordSet(Boolean(data.smtp?.password_set));
        setScannerDevice(typeof data.scanner_device === "string" ? data.scanner_device : "");
        setPrinterDevice(typeof data.printer_device === "string" ? data.printer_device : "");
        setIdScanOcr(Boolean(data.id_scan_ocr));
        setPairingPin("");
        setPairingPinSet(Boolean(data.pairing_pin_set));
        setPairedDeviceId(typeof data.paired_device_id === "string" ? data.paired_device_id : null);
        setPairedDeviceLabel(typeof data.paired_device_label === "string" ? data.paired_device_label : null);
        setPairedAt(typeof data.paired_at === "string" ? data.paired_at : null);
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

  async function unpairTablet() {
    const pw = getAdminPassword();
    if (!pw) {
      nav("/admin", { replace: true });
      return;
    }
    setBusy(true);
    try {
      const res = await fetch(apiUrl("/api/admin/unpair"), {
        method: "POST",
        headers: { "X-Admin-Password": pw },
      });
      if (!res.ok) {
        setModal({ title: "Unpair", message: await parseErrorDetail(res), variant: "error" });
        return;
      }
      setPairedDeviceId(null);
      setPairedDeviceLabel(null);
      setPairedAt(null);
      notifyPairingStateChanged();
      setModal({
        title: "Tablet Unpaired",
        message: "The station is now unpaired and ready for a new tablet to claim.",
        variant: "info",
      });
    } catch (e) {
      setModal({
        title: "Unpair",
        message: e instanceof Error ? e.message : "Network error",
        variant: "error",
      });
    } finally {
      setBusy(false);
    }
  }

  async function save() {
    const pw = getAdminPassword();
    if (!pw) {
      nav("/admin", { replace: true });
      return;
    }
    setBusy(true);
    try {
      const newAdminPw = newAdminPassword.trim();
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
          id_scan_ocr: idScanOcr,
          pairing_pin: pairingPin.trim() || undefined,
          new_admin_password: newAdminPw || undefined,
        }),
      });
      if (!res.ok) {
        setModal({ title: "Save", message: await parseErrorDetail(res), variant: "error" });
        return;
      }
      if (newAdminPw) {
        setAdminPassword(newAdminPw);
      }
      if (smtp.password) {
        setSmtpPasswordSet(true);
        setSmtp((s) => ({ ...s, password: "" }));
      }
      if (pairingPin.trim()) {
        setPairingPinSet(true);
        setPairingPin("");
      }
      setNewAdminPassword("");
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

      <div className="flex-1 min-h-0 overflow-y-auto grid grid-cols-1 gap-3 content-start pr-1">
        <h3 className="text-sm uppercase tracking-wide text-kiosk-muted">Tablet Pairing & Security</h3>
        <div className="rounded-2xl border-2 border-white/15 bg-kiosk-panel p-4 flex items-center justify-between gap-3">
          <div>
            <div className="text-base font-bold text-kiosk-text">
              {pairedDeviceId
                ? `Paired: ${pairedDeviceLabel || pairedDeviceId}`
                : "No Tablet Paired"}
            </div>
            <div className="text-xs text-kiosk-muted">
              {pairedDeviceId
                ? `Device ID: ${pairedDeviceId}${pairedAt ? ` • ${pairedAt}` : ""}`
                : "Any tablet with the Pairing PIN can claim this station"}
            </div>
          </div>
          {pairedDeviceId && (
            <KioskButton
              variant="danger"
              className="min-h-[3rem] px-4 text-sm shrink-0"
              disabled={busy}
              onClick={unpairTablet}
            >
              Unpair Tablet
            </KioskButton>
          )}
        </div>

        <div className="grid grid-cols-2 gap-3">
          <label className="text-sm text-kiosk-muted">
            New Tablet Pairing PIN (optional)
            <input
              className={`${field} mt-1`}
              type="password"
              inputMode="numeric"
              placeholder={pairingPinSet ? "Leave blank to keep current" : "Not set"}
              value={pairingPin}
              onChange={(e) => setPairingPin(e.target.value)}
            />
          </label>
          <label className="text-sm text-kiosk-muted">
            New Admin PIN (optional)
            <input
              className={`${field} mt-1`}
              type="password"
              inputMode="numeric"
              placeholder="Leave blank to keep current"
              value={newAdminPassword}
              onChange={(e) => setNewAdminPassword(e.target.value)}
            />
          </label>
        </div>

        <h3 className="text-sm uppercase tracking-wide text-kiosk-muted mt-1">Hardware</h3>
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
            placeholder={smtpPasswordSet ? "Leave blank to keep current" : "Not set"}
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
