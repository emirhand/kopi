import { Navigate, Route, Routes } from "react-router-dom";
import { AdminLogin } from "./views/AdminLogin";
import { AdminPanel } from "./views/AdminPanel";
import { CopyMenu } from "./views/CopyMenu";
import { Home } from "./views/Home";
import { IdScanWizard } from "./views/IdScanWizard";
import { ScanMenu } from "./views/ScanMenu";

export default function App() {
  return (
    <div className="h-full max-h-[100dvh] font-kiosk">
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/copy" element={<CopyMenu />} />
        <Route path="/scan" element={<ScanMenu />} />
        <Route path="/id-scan" element={<IdScanWizard />} />
        <Route path="/admin" element={<AdminLogin />} />
        <Route path="/admin/panel" element={<AdminPanel />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </div>
  );
}
