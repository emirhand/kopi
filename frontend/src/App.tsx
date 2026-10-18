import { useCallback, useEffect, useState } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import { apiUrl } from "./api";
import { AdminLogin } from "./views/AdminLogin";
import { AdminPanel } from "./views/AdminPanel";
import { CopyMenu } from "./views/CopyMenu";
import { Home } from "./views/Home";
import { IdScanWizard } from "./views/IdScanWizard";
import { PairDevice, PairingStatusData } from "./views/PairDevice";
import { ScanMenu } from "./views/ScanMenu";
import { UsbPrint } from "./views/UsbPrint";

export default function App() {
  const location = useLocation();
  const [pairStatus, setPairStatus] = useState<PairingStatusData | null>(null);

  const checkPairingStatus = useCallback(async () => {
    try {
      const res = await fetch(apiUrl("/api/pair/status"));
      if (!res.ok) return;
      const data = (await res.json()) as PairingStatusData;
      setPairStatus(data);
    } catch {
      // Keep existing state on transient network hiccup
    }
  }, []);

  useEffect(() => {
    checkPairingStatus();
    const handler = () => {
      checkPairingStatus();
    };
    window.addEventListener("kopi:pairing-check", handler);
    return () => {
      window.removeEventListener("kopi:pairing-check", handler);
    };
  }, [checkPairingStatus]);

  const isAdminRoute = location.pathname.startsWith("/admin");
  const mustShowPairingGate =
    !isAdminRoute &&
    pairStatus !== null &&
    ((pairStatus.paired && !pairStatus.caller_is_paired) ||
      (!pairStatus.paired && pairStatus.require_pairing));

  return (
    <div className="h-full max-h-[100dvh] font-kiosk">
      {mustShowPairingGate ? (
        <PairDevice status={pairStatus} onPaired={checkPairingStatus} />
      ) : (
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/copy" element={<CopyMenu />} />
          <Route path="/copy/:mode" element={<CopyMenu />} />
          <Route path="/scan" element={<ScanMenu />} />
          <Route path="/scan/:destination" element={<ScanMenu />} />
          <Route path="/usb-print" element={<UsbPrint />} />
          <Route path="/id-scan" element={<IdScanWizard />} />
          <Route path="/admin" element={<AdminLogin />} />
          <Route path="/admin/panel" element={<AdminPanel />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      )}
    </div>
  );
}
