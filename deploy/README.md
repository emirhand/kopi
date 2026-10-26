# Kopi Container Deployment Guide (Podman + Quadlet)

This directory contains the reference setup for running Kopi as a hardened, rootful **Podman** container managed by **systemd (Quadlet)** on a headless Linux appliance such as a Raspberry Pi (aarch64) or x86_64 host.

## Host Requirements

- **Linux with systemd** and **Podman >= 4.4** (for Quadlet support).
  - *Note:* Raspberry Pi OS (based on Debian 13 `trixie`) ships Podman 5.x and works out of the box. Debian 12 (`bookworm`) ships Podman 4.3, which does **not** include Quadlet.
- **Host CUPS** (`cups` package) running with the target printer already configured and shared via `/run/cups/cups.sock`.
- **Optional — Avahi** (`avahi-daemon`) on the host if using driverless network scanning (`sane-airscan` over eSCL/WSD) and `.local` mDNS hostnames.

## Quick Commands (`deploy/install.sh`)

Run all commands from the repository root:

### 1. Install (first-time setup or idempotent converge)

```bash
sudo ./deploy/install.sh install
```

Optional flags:

- `--install-deps`: install `podman`, `cups`, and `avahi-daemon` on Debian/Ubuntu hosts via `apt-get` before building.
- `--with-ocr`: include `ocrmypdf` inside the container image (larger image; off by default).
- `--extra-apt-packages "libsane-hpaio"`: install additional SANE/driver packages into the runtime image.
- `--image-tag localhost/kopi:local`: override the local image tag.

What `install` does:

1. Verifies systemd and Podman >= 4.4.
2. Builds `localhost/kopi:local` from `Containerfile`.
3. Creates `/var/lib/kopi` and `/var/lib/kopi/archive` owned by `10001:10001` (`0750`).
4. Installs `/etc/containers/systemd/kopi.container` (backing up any modified existing file to `.bak`).
5. Runs `systemctl daemon-reload` and `systemctl start kopi.service`.
   - *Boot enablement note:* Quadlet units are generated dynamically by `podman-system-generator` on `daemon-reload`. Because `kopi.container` includes `[Install] WantedBy=multi-user.target`, the generator automatically links `kopi.service` to start on boot (`systemctl enable` is not used on transient/generated Quadlet units).
6. Waits for `http://127.0.0.1:8000/api/health` to succeed and prints the station URL.

### 2. Update (rebuild image & restart service)

```bash
sudo ./deploy/install.sh update
```

- Tags the currently running image as `localhost/kopi:previous`.
- Rebuilds `localhost/kopi:local` and restarts `kopi.service` without touching `/var/lib/kopi`.
- To roll back if needed:

```bash
sudo podman tag localhost/kopi:previous localhost/kopi:local
sudo systemctl restart kopi.service
```

### 3. Uninstall

```bash
sudo ./deploy/install.sh uninstall
```

- Stops `kopi.service` and removes `/etc/containers/systemd/kopi.container`.
- Preserves `/var/lib/kopi` and built images by default. Pass `--purge` to delete them (prompts for interactive confirmation).

## Reading and Managing Credentials

### First-run generated credentials

If no external secret files are configured, Kopi generates a random 6-digit Pairing PIN and 8-digit Admin PIN on first start and writes them to `/var/lib/kopi/settings.json` (mode `0600`).

Read them on the station with:

```bash
sudo podman exec kopi kopi status --show-secrets
```

Or print the full tablet setup sheet:

```bash
sudo podman exec kopi kopi print-setup-sheet
```

### Supplying credentials via Podman secrets (Ansible / headless deployments)

1. Create the Podman secrets as root:

```bash
printf '87654321' | sudo podman secret create kopi_admin_password -
printf '123456'   | sudo podman secret create kopi_pairing_pin -
```

2. Uncomment the `Secret=` and `Environment=KOPI_*_FILE=` lines in `/etc/containers/systemd/kopi.container`:

```ini
Secret=kopi_admin_password,type=mount,target=/run/secrets/kopi_admin_password,mode=0400,uid=10001,gid=10001
Secret=kopi_pairing_pin,type=mount,target=/run/secrets/kopi_pairing_pin,mode=0400,uid=10001,gid=10001
Environment=KOPI_ADMIN_PASSWORD_FILE=/run/secrets/kopi_admin_password
Environment=KOPI_PAIRING_PIN_FILE=/run/secrets/kopi_pairing_pin
```

3. Reload and restart:

```bash
sudo systemctl daemon-reload
sudo systemctl restart kopi.service
```

Externally supplied secrets are never written into `/var/lib/kopi/settings.json` and are locked against edits in the Admin UI. If a configured `*_FILE` is missing, unreadable, or empty, Kopi refuses to start (fails closed).

## Mock Mode (Testing Without Hardware)

To test the container on a machine without a scanner or printer, uncomment `Environment=KOPI_HARDWARE_MODE=mock` in `/etc/containers/systemd/kopi.container` (or run standalone):

```bash
sudo podman run --rm -it \
  --read-only --tmpfs /tmp:rw,size=512m,mode=1777 \
  -e KOPI_HARDWARE_MODE=mock \
  -p 8000:8000 \
  -v kopi-test-data:/data:Z \
  localhost/kopi:local
```

## Logs and Station URL

- **Follow systemd unit logs:** `sudo journalctl -u kopi.service -f`
- **Follow container stdout/stderr:** `sudo podman logs -f kopi`
- **Find the station URL:** `sudo podman exec kopi kopi print-setup-sheet`
  - By default with `Network=host`, the URL is `http://<hostname>.local:8000`. Override it by setting `Environment=KOPI_PUBLIC_URL=http://<ip-or-dns>:8000` in `kopi.container`.

## Raspberry Pi Test Checklist

1. **Install:** Run `sudo ./deploy/install.sh install` on the Raspberry Pi and confirm `sudo systemctl status kopi.service` reports `active (running)`.
2. **Read PINs:** Run `sudo podman exec kopi kopi status --show-secrets` and note the Pairing PIN and Admin PIN.
3. **Open UI from tablet:** On the tablet connected to the same Wi-Fi, browse to `http://<pi-hostname>.local:8000`.
4. **Pair tablet:** Enter the 6-digit Pairing PIN and confirm the home screen unlocks.
5. **Print test:** Place a page on the scanner glass, run a 1-page Copy job, and verify the host CUPS queue prints the page.
6. **Network scan test:** Run a Scan to Archive job and verify the output file appears in `/var/lib/kopi/archive/`.
7. **Reboot persistence:** Reboot the Raspberry Pi (`sudo reboot`), wait for boot, and confirm `kopi.service` starts automatically and the tablet remains paired without re-entering the PIN.

## Known Limitations

- **USB flash drive mounting is not supported inside the container:** `src/kopi/hardware/usb.py` relies on `udisksctl` communicating with the host `udisks2` daemon over D-Bus and host mount propagation. Copy, ID Scan, Scan to Email, and Scan to Archive do not depend on it.
- **Direct USB scanners require device passthrough and group permissions:** Network eSCL/AirScan scanners work over `Network=host` (plus `/run/avahi-daemon/socket` for mDNS discovery). For USB-connected scanners, uncomment `AddDevice=/dev/bus/usb` in `kopi.container`, pass the host scanner group GID via `GroupAdd=<gid>`, and pass `--extra-apt-packages "libsane-hpaio"` (for HP USB MFPs) when building.
- **Temporary scan storage (`512m` tmpfs):** Multi-page 600 DPI color scans are assembled in `/tmp`. On stations with 4 GB+ RAM scanning large batches, increase `Tmpfs=/tmp:rw,size=512m,mode=1777` in `kopi.container`.

## Troubleshooting

- **Service fails to start / health check failing:**
  Check `sudo journalctl -u kopi.service -n 100 --no-pager`. If `/var/lib/kopi/settings.json` is corrupt or a configured `KOPI_*_FILE` secret is missing/empty, Kopi logs a `SettingsError` and exits immediately without modifying `settings.json`.
- **No printers listed in Admin Settings (`lpstat` empty):**
  Verify CUPS is running on the host (`sudo systemctl status cups`) and `/run/cups/cups.sock` exists and is world-accessible (`srw-rw-rw-`). Confirm printers are visible on the host with `lpstat -a`.
- **Scanner not found (`scanimage -L` empty):**
  - For network (eSCL/AirScan) scanners: uncomment `Volume=/run/avahi-daemon/socket:/run/avahi-daemon/socket` in `/etc/containers/systemd/kopi.container`, ensure `avahi-daemon` is running on the host, or configure the scanner's static IP in `/etc/sane.d/airscan.conf`.
  - For USB scanners: uncomment `AddDevice=/dev/bus/usb` and add `GroupAdd=<scanner-gid>` in `kopi.container`.
