import React, { useEffect } from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { installPairedFetchInterceptor } from "./api";
import App from "./App";
import "./index.css";

installPairedFetchInterceptor();


function KioskGuards({ children }: { children: React.ReactNode }) {
  useEffect(() => {
    const blockContext = (e: MouseEvent) => e.preventDefault();
    const blockGesture = (e: Event) => e.preventDefault();
    document.addEventListener("contextmenu", blockContext);
    document.addEventListener("gesturestart", blockGesture, { passive: false });
    return () => {
      document.removeEventListener("contextmenu", blockContext);
      document.removeEventListener("gesturestart", blockGesture);
    };
  }, []);
  return <>{children}</>;
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <BrowserRouter>
      <KioskGuards>
        <App />
      </KioskGuards>
    </BrowserRouter>
  </React.StrictMode>,
);
