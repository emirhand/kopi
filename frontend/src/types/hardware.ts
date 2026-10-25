export type UsbVolumeInfo = {
  device: string;
  mountpoint: string | null;
  label: string;
  model: string;
  mounted: boolean;
};

export type HardwareInfo = {
  scanners: string[];
  printers: string[];
  usb_volumes: UsbVolumeInfo[];
};

export type HardwareOptions = {
  scanners: string[];
  printers: string[];
};

export type AdminSettingsResponse = {
  smtp?: {
    host?: string;
    port?: number;
    user?: string;
    password_set?: boolean;
    from_email?: string;
    tls?: boolean;
  };
  scanner_device?: string;
  printer_device?: string;
  id_scan_ocr?: boolean;
  pairing_pin_set?: boolean;
  pairing_pin_managed?: boolean;
  admin_password_managed?: boolean;
  paired_device_id?: string | null;
  paired_device_label?: string | null;
  paired_at?: string | null;
  hardware_options?: HardwareOptions;
};
