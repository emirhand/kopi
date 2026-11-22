import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { apiUrl, notifyPairingStateChanged, parseErrorDetail } from "../api";
import { KioskButton } from "../components/KioskButton";
import { StatusModal } from "../components/StatusModal";
import type { AdminSettingsResponse, HardwareOptions } from "../types/hardware";
import { clearAdminSession, getAdminPassword, setAdminPassword } from "./AdminLogin";

type Smtp = {
  host: string;
  port: number;
  user: string;
  password: string;
  from_email: string;
  tls: boolean;
  allowed_domains: string[];
  max_attachment_mb: number;
};

const emptySmtp: Smtp = {
  host: "",
  port: 587,
  user: "",
  password: "",
  from_email: "",
  tls: true,
  allowed_domains: [],
  max_attachment_mb: 20,
};

export function AdminPanel() {
  const nav = useNavigate();
  const [smtp, setSmtp] = useState<Smtp>(emptySmtp);
  const [smtpPasswordSet, setSmtpPasswordSet] = useState(false);
  const [smtpPasswordManaged, setSmtpPasswordManaged] = useState(false);
  const [allowedDomainsText, setAllowedDomainsText] = useState("");
  const [oktaEnabled, setOktaEnabled] = useState(false);
  const [oktaDomain, setOktaDomain] = useState("");
  const [oktaApiToken, setOktaApiToken] = useState("");
  const [oktaTokenSet, setOktaTokenSet] = useState(false);
  const [oktaTokenManaged, setOktaTokenManaged] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [busy, setBusy] = useState(false);
  const [refreshingDevices, setRefreshingDevices] = useState(false);
  const [scannerDevice, setScannerDevice] = useState("");
  const [printerDevice, setPrinterDevice] = useState("");
  const [enableUsbScan, setEnableUsbScan] = useState(true);
  const [enableEmailScan, setEnableEmailScan] = useState(true);
  const [enableArchiveScan, setEnableArchiveScan] = useState(true);
  const [pairingPin, setPairingPin] = useState("");
  const [pairingPinSet, setPairingPinSet] = useState(false);
  const [pairingPinManaged, setPairingPinManaged] = useState(false);
  const [newAdminPassword, setNewAdminPassword] = useState("");
  const [adminPasswordManaged, setAdminPasswordManaged] = useState(false);
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
        const data: AdminSettingsResponse = await res.json();
        const domains = Array.isArray(data.smtp?.allowed_domains)
          ? data.smtp.allowed_domains.filter((d): d is string => typeof d === "string")
          : [];
        setSmtp({
          host: typeof data.smtp?.host === "string" ? data.smtp.host : "",
          port: typeof data.smtp?.port === "number" ? data.smtp.port : 587,
          user: typeof data.smtp?.user === "string" ? data.smtp.user : "",
          password: "",
          from_email: typeof data.smtp?.from_email === "string" ? data.smtp.from_email : "",
          tls: typeof data.smtp?.tls === "boolean" ? data.smtp.tls : true,
          allowed_domains: domains,
          max_attachment_mb: typeof data.smtp?.max_attachment_mb === "number" ? data.smtp.max_attachment_mb : 20,
        });
        setAllowedDomainsText(domains.join(", "));
        setSmtpPasswordSet(Boolean(data.smtp?.password_set));
        setSmtpPasswordManaged(Boolean(data.smtp?.password_managed));
        setOktaEnabled(Boolean(data.okta?.enabled));
        setOktaDomain(typeof data.okta?.domain === "string" ? data.okta.domain : "");
        setOktaApiToken("");
        setOktaTokenSet(Boolean(data.okta?.api_token_set));
        setOktaTokenManaged(Boolean(data.okta?.api_token_managed));
        setScannerDevice(typeof data.scanner_device === "string" ? data.scanner_device : "");
        setPrinterDevice(typeof data.printer_device === "string" ? data.printer_device : "");
        setEnableUsbScan(data.enable_usb_scan !== false);
        setEnableEmailScan(data.enable_email_scan !== false);
        setEnableArchiveScan(data.enable_archive_scan !== false);
        setPairingPin("");
        setPairingPinSet(Boolean(data.pairing_pin_set));
        setPairingPinManaged(Boolean(data.pairing_pin_managed));
        setAdminPasswordManaged(Boolean(data.admin_password_managed));
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

  async function refreshDevices() {
    const pw = getAdminPassword();
    if (!pw) {
      nav("/admin", { replace: true });
      return;
    }
    setRefreshingDevices(true);
    try {
      const res = await fetch(apiUrl("/api/admin/settings?refresh=1"), {
        headers: { "X-Admin-Password": pw },
      });
      if (res.status === 401 || res.status === 403) {
        clearAdminSession();
        nav("/admin", { replace: true });
        return;
      }
      if (!res.ok) {
        setModal({ title: "Hardware", message: await parseErrorDetail(res), variant: "error" });
        return;
      }
      const data: AdminSettingsResponse = await res.json();
      setHardwareOptions({
        scanners: Array.isArray(data?.hardware_options?.scanners) ? data.hardware_options.scanners : [],
        printers: Array.isArray(data?.hardware_options?.printers) ? data.hardware_options.printers : [],
      });
    } catch (e) {
      setModal({
        title: "Hardware",
        message: e instanceof Error ? e.message : "Network error",
        variant: "error",
      });
    } finally {
      setRefreshingDevices(false);
    }
  }

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
      const newAdminPw = adminPasswordManaged ? "" : newAdminPassword.trim();
      const newPin = pairingPinManaged ? "" : pairingPin.trim();
      const res = await fetch(apiUrl("/api/admin/settings"), {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
          "X-Admin-Password": pw,
        },
        body: JSON.stringify({
          smtp: {
            ...smtp,
            allowed_domains: allowedDomainsText
              .split(",")
              .map((d) => d.trim().replace(/^@+/, "").toLowerCase())
              .filter(Boolean),
          },
          okta: {
            enabled: oktaEnabled,
            domain: oktaDomain.trim(),
            api_token: oktaTokenManaged ? "" : oktaApiToken.trim(),
          },
          scanner_device: scannerDevice,
          printer_device: printerDevice,
          enable_usb_scan: enableUsbScan,
          enable_email_scan: enableEmailScan,
          enable_archive_scan: enableArchiveScan,
          pairing_pin: newPin || undefined,
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
      if (oktaApiToken.trim()) {
        setOktaTokenSet(true);
        setOktaApiToken("");
      }
      if (newPin) {
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
              className={`${field} mt-1 ${pairingPinManaged ? "opacity-60 cursor-not-allowed" : ""}`}
              type="password"
              inputMode="numeric"
              disabled={pairingPinManaged}
              placeholder={
                pairingPinManaged
                  ? "Managed by the station's deployment"
                  : pairingPinSet
                    ? "Leave blank to keep current"
                    : "Not set"
              }
              value={pairingPin}
              onChange={(e) => setPairingPin(e.target.value)}
            />
            {pairingPinManaged && (
              <span className="mt-1 block text-xs text-kiosk-muted">
                Managed by the station's deployment
              </span>
            )}
          </label>
          <label className="text-sm text-kiosk-muted">
            New Admin PIN (optional)
            <input
              className={`${field} mt-1 ${adminPasswordManaged ? "opacity-60 cursor-not-allowed" : ""}`}
              type="password"
              inputMode="numeric"
              disabled={adminPasswordManaged}
              placeholder={
                adminPasswordManaged
                  ? "Managed by the station's deployment"
                  : "Leave blank to keep current"
              }
              value={newAdminPassword}
              onChange={(e) => setNewAdminPassword(e.target.value)}
            />
            {adminPasswordManaged && (
              <span className="mt-1 block text-xs text-kiosk-muted">
                Managed by the station's deployment
              </span>
            )}
          </label>
        </div>

        <div className="flex items-center justify-between gap-3 mt-1">
          <div>
            <h3 className="text-sm uppercase tracking-wide text-kiosk-muted">Hardware</h3>
            <p className="text-xs text-kiosk-muted">
              Uses Linux CUPS &amp; SANE discovery (plug-and-play IPP Everywhere / AirPrint / eSCL).
            </p>
          </div>
          <KioskButton
            variant="secondary"
            className="shrink-0 min-h-[2.75rem] px-4 text-sm"
            disabled={busy || refreshingDevices}
            onClick={refreshDevices}
          >
            {refreshingDevices ? "Refreshing…" : "Refresh Devices"}
          </KioskButton>
        </div>
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
        <h3 className="text-sm uppercase tracking-wide text-kiosk-muted mt-1">Scan features</h3>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          <KioskButton
            variant={enableUsbScan ? "primary" : "secondary"}
            className="w-full text-lg min-h-[3.5rem]"
            onClick={() => setEnableUsbScan((v) => !v)}
          >
            USB Scan: {enableUsbScan ? "On" : "Off"}
          </KioskButton>
          <KioskButton
            variant={enableEmailScan ? "primary" : "secondary"}
            className="w-full text-lg min-h-[3.5rem]"
            onClick={() => setEnableEmailScan((v) => !v)}
          >
            Email Scan: {enableEmailScan ? "On" : "Off"}
          </KioskButton>
          <KioskButton
            variant={enableArchiveScan ? "primary" : "secondary"}
            className="w-full text-lg min-h-[3.5rem]"
            onClick={() => setEnableArchiveScan((v) => !v)}
          >
            Archive Scan: {enableArchiveScan ? "On" : "Off"}
          </KioskButton>
        </div>
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
            disabled={smtpPasswordManaged}
            placeholder={
              smtpPasswordManaged
                ? "Managed via environment / secret file"
                : smtpPasswordSet
                  ? "Leave blank to keep current"
                  : "Not set"
            }
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
        <label className="text-sm text-kiosk-muted">
          Allowed Email Domains (comma-separated, blank = any)
          <input
            className={`${field} mt-1`}
            placeholder="e.g. company.com, partner.org"
            value={allowedDomainsText}
            onChange={(e) => setAllowedDomainsText(e.target.value)}
            autoComplete="off"
          />
        </label>
        <label className="text-sm text-kiosk-muted">
          Max Attachment Size (MB)
          <input
            className={`${field} mt-1`}
            type="number"
            min={1}
            max={100}
            inputMode="numeric"
            value={smtp.max_attachment_mb}
            onChange={(e) =>
              setSmtp((s) => ({
                ...s,
                max_attachment_mb: Math.max(1, Math.min(100, Number(e.target.value) || 20)),
              }))
            }
          />
        </label>

        <h3 className="text-sm uppercase tracking-wide text-kiosk-muted mt-1">
          Okta Directory Verification (Scan-to-Email)
        </h3>
        <KioskButton
          variant={oktaEnabled ? "primary" : "secondary"}
          className="w-full text-lg min-h-[3.5rem]"
          onClick={() => setOktaEnabled((v) => !v)}
        >
          Require Active Okta User: {oktaEnabled ? "On" : "Off"}
        </KioskButton>
        <label className="text-sm text-kiosk-muted">
          Okta Domain
          <input
            className={`${field} mt-1`}
            placeholder="https://company.okta.com"
            value={oktaDomain}
            onChange={(e) => setOktaDomain(e.target.value)}
            autoComplete="off"
          />
        </label>
        <label className="text-sm text-kiosk-muted">
          Okta API Token (SSWS)
          <input
            className={`${field} mt-1`}
            type="password"
            disabled={oktaTokenManaged}
            placeholder={
              oktaTokenManaged
                ? "Managed via environment / secret file"
                : oktaTokenSet
                  ? "Leave blank to keep current"
                  : "Not set"
            }
            value={oktaApiToken}
            onChange={(e) => setOktaApiToken(e.target.value)}
            autoComplete="new-password"
          />
        </label>
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
