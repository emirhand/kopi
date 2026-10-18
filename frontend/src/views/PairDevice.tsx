import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { apiUrl, parseErrorDetail, setDeviceToken } from "../api";
import { KioskButton } from "../components/KioskButton";
import { StatusModal } from "../components/StatusModal";

export type PairingStatusData = {
  paired: boolean;
  require_pairing: boolean;
  caller_is_paired: boolean;
  device_id: string | null;
  device_label: string | null;
  paired_at: string | null;
};

type Props = {
  status: PairingStatusData;
  onPaired: () => void;
};

const KEYS = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "Clear", "0", "⌫"] as const;

function detectDefaultTabletLabel(): string {
  const ua = typeof navigator !== "undefined" ? navigator.userAgent : "";
  if (/iPad/i.test(ua)) return "iPad Kiosk";
  if (/Android/i.test(ua)) return "Android Tablet";
  return "Control Tablet";
}

export function PairDevice({ status, onPaired }: Props) {
  const nav = useNavigate();
  const isLockedToOther = status.paired && !status.caller_is_paired;

  const [replaceMode, setReplaceMode] = useState(false);
  const [pin, setPin] = useState("");
  const [deviceLabel, setDeviceLabel] = useState(detectDefaultTabletLabel);
  const [busy, setBusy] = useState(false);
  const [modal, setModal] = useState<{ title: string; message: string; variant: "info" | "error" } | null>(
    null,
  );

  function onKey(k: (typeof KEYS)[number]) {
    if (k === "Clear") {
      setPin("");
      return;
    }
    if (k === "⌫") {
      setPin((p) => p.slice(0, -1));
      return;
    }
    setPin((p) => (p.length < 12 ? p + k : p));
  }

  async function submitPairing() {
    if (!pin) return;
    setBusy(true);
    try {
      const endpoint = isLockedToOther ? "/api/pair/replace" : "/api/pair/claim";
      const payload = isLockedToOther
        ? { admin_password: pin, device_label: deviceLabel.trim() || "Replacement Tablet" }
        : { pin, device_label: deviceLabel.trim() || "Paired Tablet" };

      const res = await fetch(apiUrl(endpoint), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!res.ok) {
        setModal({
          title: isLockedToOther ? "Replace Tablet Failed" : "Pairing Failed",
          message: await parseErrorDetail(res),
          variant: "error",
        });
        return;
      }
      const data = await res.json();
      if (typeof data?.token === "string" && data.token) {
        setDeviceToken(data.token);
      }
      setPin("");
      onPaired();
    } catch (e) {
      setModal({
        title: "Network Error",
        message: e instanceof Error ? e.message : "Failed to reach Kopi station",
        variant: "error",
      });
    } finally {
      setBusy(false);
    }
  }

  if (isLockedToOther && !replaceMode) {
    return (
      <div className="h-full flex flex-col justify-between bg-kiosk-bg p-5 gap-4 overflow-hidden">
        <header className="shrink-0 flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold tracking-tight text-kiosk-text">Station Locked</h1>
            <p className="text-sm text-kiosk-muted">Exclusive Single-Tablet Access Control</p>
          </div>
          <KioskButton
            variant="ghost"
            className="min-h-[3rem] px-4 text-base"
            onClick={() => nav("/admin")}
          >
            🔒 Admin
          </KioskButton>
        </header>

        <div className="flex-1 flex flex-col items-center justify-center text-center gap-4 rounded-2xl border-2 border-white/15 bg-kiosk-panel p-6">
          <div className="text-5xl">🔐</div>
          <h2 className="text-2xl font-bold text-kiosk-text">
            Paired to {status.device_label || "Another Tablet"}
          </h2>
          <p className="text-base text-kiosk-muted max-w-md">
            This Kopi station is exclusively locked to its paired control tablet
            {status.paired_at ? ` (paired ${status.paired_at})` : ""}.
          </p>
          <p className="text-sm text-kiosk-muted max-w-md">
            If the original tablet was lost, damaged, or had its browser storage cleared, you can
            transfer pairing to this device using the Admin PIN.
          </p>
        </div>

        <div className="shrink-0 grid grid-cols-2 gap-3">
          <KioskButton
            variant="secondary"
            className="text-lg min-h-[4rem]"
            onClick={onPaired}
          >
            🔄 Retry Check
          </KioskButton>
          <KioskButton
            variant="primary"
            className="text-lg min-h-[4rem]"
            onClick={() => {
              setPin("");
              setReplaceMode(true);
            }}
          >
            🛠️ Replace via Admin PIN
          </KioskButton>
        </div>
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col justify-between bg-kiosk-bg p-4 gap-2 overflow-hidden">
      <div className="shrink-0 flex items-center justify-between gap-2">
        <div>
          <h1 className="text-xl font-bold text-kiosk-text">
            {isLockedToOther ? "Replace Paired Tablet (Admin PIN)" : "Pair Control Tablet"}
          </h1>
          <p className="text-xs text-kiosk-muted">
            {isLockedToOther
              ? "Enter the Admin PIN to revoke the previous tablet and pair this device"
              : "Enter the Station Pairing PIN to lock this copier to this tablet"}
          </p>
        </div>
        {isLockedToOther ? (
          <KioskButton
            variant="ghost"
            className="min-h-[2.75rem] px-3 text-sm"
            onClick={() => setReplaceMode(false)}
          >
            Cancel
          </KioskButton>
        ) : (
          <KioskButton
            variant="ghost"
            className="min-h-[2.75rem] px-3 text-sm"
            onClick={() => nav("/admin")}
          >
            🔒 Admin
          </KioskButton>
        )}
      </div>

      <div className="shrink-0 grid grid-cols-2 gap-2">
        <label className="flex flex-col text-xs text-kiosk-muted">
          Tablet Label
          <input
            type="text"
            value={deviceLabel}
            onChange={(e) => setDeviceLabel(e.target.value)}
            placeholder="e.g. Front Desk iPad"
            className="mt-1 rounded-xl border-2 border-white/20 bg-kiosk-panel px-3 py-2 text-base font-semibold text-kiosk-text outline-none focus:border-kiosk-accent"
          />
        </label>
        <div className="flex flex-col text-xs text-kiosk-muted">
          {isLockedToOther ? "Admin PIN" : "Pairing PIN"}
          <div className="mt-1 rounded-xl border-2 border-white/20 bg-kiosk-panel px-3 py-2 text-center text-xl tracking-[0.4em] font-mono text-kiosk-text min-h-[2.75rem] flex items-center justify-center">
            {pin ? "•".repeat(pin.length) : <span className="text-kiosk-muted text-sm tracking-normal">Enter PIN</span>}
          </div>
        </div>
      </div>

      <div className="flex-1 min-h-0 grid grid-cols-3 gap-2">
        {KEYS.map((k) => (
          <KioskButton
            key={k}
            variant="secondary"
            className="min-h-0 h-full text-2xl font-bold"
            onClick={() => onKey(k)}
          >
            {k}
          </KioskButton>
        ))}
      </div>

      <KioskButton
        variant="primary"
        className="shrink-0 w-full text-xl min-h-[3.75rem]"
        disabled={busy || !pin}
        onClick={submitPairing}
      >
        {busy
          ? "Pairing…"
          : isLockedToOther
            ? "Revoke Old Tablet & Pair This Device"
            : "Pair This Tablet"}
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
