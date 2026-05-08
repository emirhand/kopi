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
