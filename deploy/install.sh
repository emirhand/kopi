#!/usr/bin/env bash
# Build, install, update, or uninstall the Kopi Podman Quadlet service.
set -euo pipefail

ACTION="install"
WITH_OCR="0"
IMAGE_TAG="localhost/kopi:local"
PREVIOUS_TAG="localhost/kopi:previous"
INSTALL_DEPS="0"
PURGE="0"
EXTRA_APT_PACKAGES=""
PORT="${PORT:-8000}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

QUADLET_DIR="${KOPI_QUADLET_DIR:-/etc/containers/systemd}"
QUADLET_DEST="${QUADLET_DIR}/kopi.container"
QUADLET_NEW="${QUADLET_DIR}/kopi.container.new"
QUADLET_HASH_FILE="${QUADLET_DIR}/.kopi.container.sha256"
QUADLET_SRC="${KOPI_QUADLET_SRC:-${SCRIPT_DIR}/quadlet/kopi.container}"

DATA_DIR="/var/lib/kopi"
SERVICE_NAME="kopi.service"
KOPI_UID="10001"
KOPI_GID="10001"

usage() {
    cat <<'EOF'
Usage:
  sudo ./deploy/install.sh [install|update|uninstall] [options]

Actions:
  install                   Build image, configure /var/lib/kopi, install Quadlet
                            unit, and start kopi.service (default).
  update                    Tag current image as localhost/kopi:previous, rebuild
                            image, apply unit updates, and restart kopi.service.
  uninstall                 Stop kopi.service and remove the Quadlet unit
                            (preserves /var/lib/kopi and images unless --purge).

Options:
  --with-ocr                Include ocrmypdf in the container image build.
  --extra-apt-packages STR  Space-separated extra apt packages for the image.
  --image-tag TAG           Container image tag (default: localhost/kopi:local).
  --install-deps            Install host packages via apt-get (podman + catatonit
                            with recommends; cups and avahi-daemon without).
  --purge                   With uninstall: also delete /var/lib/kopi and images
                            (prompts for confirmation).
  -h, --help                Show this help text.

Environment overrides:
  PORT                      Station HTTP port waited on by health check (default: 8000).
                            Export PORT before running this script if overridden in
                            kopi.container.
EOF
}

die() {
    printf 'Error: %s\n' "$*" >&2
    exit 1
}

info() {
    printf '==> %s\n' "$*"
}

warn() {
    printf 'WARNING: %s\n' "$*" >&2
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        install|update|uninstall|render-unit)
            ACTION="$1"
            shift
            ;;
        --with-ocr)
            WITH_OCR="1"
            shift
            ;;
        --extra-apt-packages)
            [ "$#" -ge 2 ] || die "--extra-apt-packages requires a value"
            EXTRA_APT_PACKAGES="$2"
            shift 2
            ;;
        --image-tag)
            [ "$#" -ge 2 ] || die "--image-tag requires a value"
            IMAGE_TAG="$2"
            shift 2
            ;;
        --install-deps)
            INSTALL_DEPS="1"
            shift
            ;;
        --purge)
            PURGE="1"
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            die "Unknown argument: $1 (run with --help for usage)"
            ;;
    esac
done

file_sha256() {
    local target_file="$1"
    local sum_line
    sum_line="$(sha256sum "${target_file}")"
    printf '%s\n' "${sum_line%% *}"
}

install_quadlet_unit() {
    [ -f "${QUADLET_SRC}" ] || die "Quadlet template not found at ${QUADLET_SRC}"
    install -d -m 0755 "${QUADLET_DIR}"

    local tmp_unit
    tmp_unit="$(mktemp "${QUADLET_DIR}/.kopi.container.XXXXXX")"
    trap 'rm -f "${tmp_unit}"' RETURN

    sed "s|^Image=.*|Image=${IMAGE_TAG}|" "${QUADLET_SRC}" > "${tmp_unit}"
    chmod 0644 "${tmp_unit}"

    local rendered_hash
    rendered_hash="$(file_sha256 "${tmp_unit}")"

    if [ ! -f "${QUADLET_DEST}" ]; then
        info "Installing Quadlet unit to ${QUADLET_DEST}..."
        mv -f "${tmp_unit}" "${QUADLET_DEST}"
        printf '%s\n' "${rendered_hash}" > "${QUADLET_HASH_FILE}"
        chmod 0644 "${QUADLET_HASH_FILE}"
        rm -f "${QUADLET_NEW}"
        trap - RETURN
        return 0
    fi

    local current_hash
    current_hash="$(file_sha256 "${QUADLET_DEST}")"

    local recorded_hash=""
    if [ -f "${QUADLET_HASH_FILE}" ]; then
        recorded_hash="$(tr -d '[:space:]' < "${QUADLET_HASH_FILE}")"
    fi

    if [ "${current_hash}" = "${rendered_hash}" ]; then
        info "Quadlet unit ${QUADLET_DEST} is already up to date (no changes)."
        rm -f "${tmp_unit}" "${QUADLET_NEW}"
        if [ "${recorded_hash}" != "${rendered_hash}" ]; then
            printf '%s\n' "${rendered_hash}" > "${QUADLET_HASH_FILE}"
            chmod 0644 "${QUADLET_HASH_FILE}"
        fi
        trap - RETURN
        return 0
    fi

    if [ -n "${recorded_hash}" ] && [ "${current_hash}" = "${recorded_hash}" ]; then
        info "Updating unmodified Quadlet unit ${QUADLET_DEST}..."
        mv -f "${tmp_unit}" "${QUADLET_DEST}"
        printf '%s\n' "${rendered_hash}" > "${QUADLET_HASH_FILE}"
        chmod 0644 "${QUADLET_HASH_FILE}"
        rm -f "${QUADLET_NEW}"
        trap - RETURN
        return 0
    fi

    warn "Existing ${QUADLET_DEST} was modified by the operator; keeping existing file."
    mv -f "${tmp_unit}" "${QUADLET_NEW}"
    chmod 0644 "${QUADLET_NEW}"
    warn "Wrote new unit template to ${QUADLET_NEW}."
    warn "Review changes with: diff -u ${QUADLET_DEST} ${QUADLET_NEW}"
    trap - RETURN
}

if [ "${ACTION}" = "render-unit" ]; then
    install_quadlet_unit
    exit 0
fi

if [ "$(id -u)" -ne 0 ]; then
    die "This script must be run as root (for example: sudo ./deploy/install.sh ${ACTION})."
fi

maybe_install_host_deps() {
    if [ "${INSTALL_DEPS}" != "1" ]; then
        return 0
    fi
    if ! command -v apt-get >/dev/null 2>&1; then
        die "--install-deps was requested, but apt-get is not available on this host."
    fi
    info "Installing host packages (podman + catatonit with recommends; cups, avahi-daemon)..."
    export DEBIAN_FRONTEND=noninteractive
    apt-get update
    apt-get install -y podman catatonit
    apt-get install -y --no-install-recommends cups avahi-daemon
}

check_catatonit() {
    if command -v catatonit >/dev/null 2>&1; then
        return 0
    fi
    if [ -x /usr/libexec/podman/catatonit ] || [ -x /usr/lib/podman/catatonit ]; then
        return 0
    fi
    die "catatonit init binary not found (required by RunInit=true in kopi.container). Install it with 'sudo apt-get install -y catatonit' or re-run with --install-deps."
}

check_cups_warning() {
    local cups_unit_known="0"
    local unit_list
    unit_list="$(systemctl list-unit-files cups.socket cups.service 2>/dev/null || true)"
    if printf '%s\n' "${unit_list}" | grep -qE '^(cups\.socket|cups\.service)[[:space:]]'; then
        cups_unit_known="1"
    fi
    if [ "${cups_unit_known}" != "1" ] || [ ! -S /run/cups/cups.sock ]; then
        warn "Host CUPS (cups.socket / /run/cups/cups.sock) is not active or not installed. Printing will not work until host CUPS is installed (see --install-deps) and a printer queue is added."
    fi
}

check_requirements() {
    if ! command -v systemctl >/dev/null 2>&1 || [ ! -d /run/systemd/system ]; then
        die "systemd is required but does not appear to be running on this host."
    fi
    if ! command -v podman >/dev/null 2>&1; then
        die "podman is not installed. Install Podman >= 4.4 (or re-run with --install-deps on Debian trixie / Raspberry Pi OS)."
    fi

    local raw_ver ver major minor
    raw_ver="$(podman --version 2>/dev/null || true)"
    ver="$(printf '%s\n' "${raw_ver}" | awk '{for (i=1; i<=NF; i++) if ($i ~ /^[0-9]+\.[0-9]+/) {print $i; exit}}')"
    if [ -z "${ver}" ]; then
        die "Could not parse Podman version from: ${raw_ver}"
    fi
    major="${ver%%.*}"
    minor="${ver#*.}"
    minor="${minor%%.*}"

    if [ "${major}" -lt 4 ] || { [ "${major}" -eq 4 ] && [ "${minor}" -lt 4 ]; }; then
        die "Podman ${ver} is too old. Quadlet requires Podman >= 4.4 (Debian bookworm ships 4.3; upgrade to Debian trixie / Raspberry Pi OS trixie or newer)."
    fi

    check_catatonit
    check_cups_warning
}

resolve_version_metadata() {
    KOPI_VERSION="0.1.0"
    if [ -f "${REPO_ROOT}/pyproject.toml" ]; then
        local parsed_ver
        parsed_ver="$(awk -F'"' '/^version[[:space:]]*=[[:space:]]*"/ {print $2; exit}' "${REPO_ROOT}/pyproject.toml" || true)"
        if [ -n "${parsed_ver}" ]; then
            KOPI_VERSION="${parsed_ver}"
        fi
    fi

    VCS_REF="unknown"
    if command -v git >/dev/null 2>&1 && [ -d "${REPO_ROOT}/.git" ]; then
        VCS_REF="$(git -C "${REPO_ROOT}" rev-parse --short HEAD 2>/dev/null || printf 'unknown')"
    fi
}

build_image() {
    resolve_version_metadata
    info "Building container image ${IMAGE_TAG} (version=${KOPI_VERSION}, ref=${VCS_REF}, with_ocr=${WITH_OCR})..."
    podman build \
        --tag "${IMAGE_TAG}" \
        --build-arg "KOPI_VERSION=${KOPI_VERSION}" \
        --build-arg "VCS_REF=${VCS_REF}" \
        --build-arg "WITH_OCR=${WITH_OCR}" \
        --build-arg "EXTRA_APT_PACKAGES=${EXTRA_APT_PACKAGES}" \
        --file "${REPO_ROOT}/Containerfile" \
        "${REPO_ROOT}"
}

ensure_data_dir() {
    info "Ensuring ${DATA_DIR} exists with owner ${KOPI_UID}:${KOPI_GID} and mode 0750..."
    install -d -m 0750 -o "${KOPI_UID}" -g "${KOPI_GID}" "${DATA_DIR}"
    install -d -m 0750 -o "${KOPI_UID}" -g "${KOPI_GID}" "${DATA_DIR}/archive"
}

wait_for_health() {
    local attempts=30
    local i=1
    local health_url="http://127.0.0.1:${PORT}/api/health"
    info "Waiting for Kopi health endpoint (${health_url})..."
    while [ "${i}" -le "${attempts}" ]; do
        if command -v curl >/dev/null 2>&1; then
            if curl -fsS --max-time 2 "${health_url}" >/dev/null 2>&1; then
                return 0
            fi
        elif command -v python3 >/dev/null 2>&1; then
            if python3 -c "import urllib.request; urllib.request.urlopen('${health_url}', timeout=2)" >/dev/null 2>&1; then
                return 0
            fi
        fi
        sleep 1
        i=$((i + 1))
    done
    die "Timed out waiting for ${health_url}. Check logs with: sudo journalctl -u ${SERVICE_NAME} -n 50 --no-pager"
}

print_post_install() {
    local host_name
    host_name="$(hostname 2>/dev/null || printf 'localhost')"
    cat <<EOF

Kopi is running and healthy!
  Station URL (LAN) : http://${host_name}.local:${PORT}
  Service status    : sudo systemctl status ${SERVICE_NAME}
  View credentials  : sudo podman exec kopi kopi status --show-secrets
  Print setup sheet : sudo podman exec kopi kopi print-setup-sheet
EOF
}

do_install() {
    maybe_install_host_deps
    check_requirements
    build_image
    ensure_data_dir
    install_quadlet_unit
    info "Reloading systemd (Quadlet generator wires boot enablement from [Install])..."
    systemctl daemon-reload
    info "Starting ${SERVICE_NAME}..."
    systemctl start "${SERVICE_NAME}"
    wait_for_health
    print_post_install
}

do_update() {
    check_requirements
    if podman image exists "${IMAGE_TAG}"; then
        info "Tagging existing ${IMAGE_TAG} as ${PREVIOUS_TAG} for rollback..."
        podman tag "${IMAGE_TAG}" "${PREVIOUS_TAG}"
    fi
    build_image
    install_quadlet_unit
    systemctl daemon-reload
    info "Restarting ${SERVICE_NAME}..."
    systemctl restart "${SERVICE_NAME}"
    wait_for_health
    cat <<EOF

Update complete! ${DATA_DIR} was preserved.
To roll back to the previous image if needed:
  sudo podman tag ${PREVIOUS_TAG} ${IMAGE_TAG} && sudo systemctl restart ${SERVICE_NAME}
EOF
}

do_uninstall() {
    if command -v systemctl >/dev/null 2>&1 && [ -d /run/systemd/system ]; then
        if systemctl is-active --quiet "${SERVICE_NAME}"; then
            info "Stopping ${SERVICE_NAME}..."
            systemctl stop "${SERVICE_NAME}"
        fi
    fi

    if [ -f "${QUADLET_DEST}" ] || [ -f "${QUADLET_NEW}" ] || [ -f "${QUADLET_HASH_FILE}" ]; then
        info "Removing Quadlet unit and metadata from ${QUADLET_DIR}..."
        rm -f "${QUADLET_DEST}" "${QUADLET_NEW}" "${QUADLET_HASH_FILE}"
    fi

    if command -v systemctl >/dev/null 2>&1 && [ -d /run/systemd/system ]; then
        systemctl daemon-reload
    fi

    if [ "${PURGE}" = "1" ]; then
        printf 'WARNING: --purge will permanently delete %s and local Kopi container images.\n' "${DATA_DIR}"
        local confirm=""
        read -r -p "Type 'yes' to confirm purge: " confirm
        if [ "${confirm}" = "yes" ]; then
            info "Removing ${DATA_DIR}..."
            rm -rf "${DATA_DIR}"
            if command -v podman >/dev/null 2>&1; then
                podman rmi -f "${IMAGE_TAG}" "${PREVIOUS_TAG}" 2>/dev/null || true
            fi
            info "Purge complete."
        else
            info "Purge aborted; ${DATA_DIR} and images were kept."
        fi
    else
        info "Uninstalled ${SERVICE_NAME}. Data in ${DATA_DIR} and container images were preserved (pass --purge to remove them)."
    fi
}

case "${ACTION}" in
    install)
        do_install
        ;;
    update)
        do_update
        ;;
    uninstall)
        do_uninstall
        ;;
esac
