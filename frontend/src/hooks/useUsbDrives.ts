import { useCallback, useEffect, useState } from "react";
import { apiUrl } from "../api";

export interface UsbDriveInfo {
  device: string;
  mountpoint: string | null;
  label: string;
  model: string;
  mounted: boolean;
  fstype: string;
  size: string;
}

export function useUsbDrives(enabled: boolean = true) {
  const [usbDrives, setUsbDrives] = useState<UsbDriveInfo[]>([]);
  const [selectedDevice, setSelectedDevice] = useState<string>("");
  const [loadingDrives, setLoadingDrives] = useState(false);

  const fetchDrives = useCallback(async () => {
    setLoadingDrives(true);
    try {
      const res = await fetch(apiUrl("/api/scan/usb/drives"));
      if (!res.ok) return;
      const data = await res.json();
      const drives: UsbDriveInfo[] = Array.isArray(data?.drives) ? data.drives : [];
      setUsbDrives(drives);
      setSelectedDevice((prev) => {
        if (prev && drives.some((d) => d.device === prev)) return prev;
        return drives[0]?.device ?? "";
      });
    } catch {
      /* ignore */
    } finally {
      setLoadingDrives(false);
    }
  }, []);

  useEffect(() => {
    if (enabled) {
      void fetchDrives();
    }
  }, [enabled, fetchDrives]);

  const selectedDrive = usbDrives.find((d) => d.device === selectedDevice) ?? null;

  return {
    usbDrives,
    selectedDevice,
    setSelectedDevice,
    selectedDrive,
    loadingDrives,
    fetchDrives,
  };
}
