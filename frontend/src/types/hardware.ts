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
    password_managed?: boolean;
    from_email?: string;
    tls?: boolean;
    allowed_domains?: string[];
    max_attachment_mb?: number;
  };
  okta?: {
    enabled?: boolean;
    domain?: string;
    api_token_set?: boolean;
    api_token_managed?: boolean;
  };
  scanner_device?: string;
  printer_device?: string;
  enable_usb_scan?: boolean;
  enable_email_scan?: boolean;
  enable_archive_scan?: boolean;
  pairing_pin_set?: boolean;
  pairing_pin_managed?: boolean;
  admin_password_managed?: boolean;
  paired_device_id?: string | null;
  paired_device_label?: string | null;
  paired_at?: string | null;
  hardware_options?: HardwareOptions;
};
