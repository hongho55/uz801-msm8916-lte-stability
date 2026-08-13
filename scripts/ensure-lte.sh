#!/bin/sh
# Recovery watchdog for a UZ801/MSM8916 false-connected LTE data path.
# Review every variable before installation.
set -u

TAG=${TAG:-ensure-lte}
MODEM_IF=${MODEM_IF:-modem}
NETDEV=${NETDEV:-wwan0}
QMI_DEV=${QMI_DEV:-/dev/wwan0qmi0}
RPROC=${RPROC:-/sys/class/remoteproc/remoteproc0/state}
PROBE_HOST=${PROBE_HOST:-1.1.1.1}
PROBE_INTERVAL=${PROBE_INTERVAL:-300}
RECOVERY_TUNNEL_IF=${RECOVERY_TUNNEL_IF:-}
EXPECTED_APN=${EXPECTED_APN:-}
PROFILE_ID=${PROFILE_ID:-3}
LOCK=${LOCK:-/var/lock/ensure-lte.lock}
HEALTH=${HEALTH:-/tmp/ensure-lte.health}

log() { logger -t "$TAG" -- "$*"; }
modem_id() {
    mmcli -L 2>/dev/null |
        sed -n 's#.*Modem/\([0-9][0-9]*\).*#\1#p' | head -1
}
netif_up() {
    ifstatus "$MODEM_IF" 2>/dev/null |
        jsonfilter -e '@.up' 2>/dev/null | grep -qx true
}
probe() { ping -I "$NETDEV" -c 1 -W 3 "$PROBE_HOST" >/dev/null 2>&1; }
mark_healthy() { date +%s > "$HEALTH"; }
probe_due() {
    now=$(date +%s)
    last=0
    [ -f "$HEALTH" ] && read -r last < "$HEALTH"
    case "$last" in ''|*[!0-9]*) last=0;; esac
    [ $((now - last)) -ge "$PROBE_INTERVAL" ]
}
wait_real_lte() {
    n=0
    while [ "$n" -lt 15 ]; do
        if netif_up && probe; then
            mark_healthy
            return 0
        fi
        n=$((n + 1))
        sleep 3
    done
    return 1
}
restart_tunnel() {
    [ -n "$RECOVERY_TUNNEL_IF" ] || return 0
    ubus call "network.interface.$RECOVERY_TUNNEL_IF" down >/dev/null 2>&1 || true
    sleep 1
    ubus call "network.interface.$RECOVERY_TUNNEL_IF" up >/dev/null 2>&1 ||
        ifup "$RECOVERY_TUNNEL_IF" >/dev/null 2>&1 || true
}

mkdir "$LOCK" 2>/dev/null || exit 0
trap 'rmdir "$LOCK"' EXIT

if netif_up && ! probe_due; then
    exit 0
fi
if netif_up && probe; then
    mark_healthy
    if [ -n "$RECOVERY_TUNNEL_IF" ]; then
        ip link show "$RECOVERY_TUNNEL_IF" >/dev/null 2>&1 || restart_tunnel
    fi
    exit 0
fi

log 'real LTE probe failed; starting bounded recovery'
rm -f "$HEALTH"

n=0
mid=''
while [ "$n" -lt 15 ]; do
    mid=$(modem_id)
    [ -c "$QMI_DEV" ] && [ -n "$mid" ] && break
    n=$((n + 1))
    sleep 2
done

if [ ! -c "$QMI_DEV" ] || [ -z "$mid" ]; then
    /etc/init.d/modemmanager restart >/dev/null 2>&1 || true
    sleep 8
    mid=$(modem_id)
fi

# Optional and carrier-specific: repair one configured attach profile only.
if [ -n "$EXPECTED_APN" ] && [ -c "$QMI_DEV" ] && [ -n "$mid" ]; then
    profiles=$(qmicli -d "$QMI_DEV" --device-open-proxy \
        --wds-get-profile-list=3gpp 2>/dev/null || true)
    if ! printf '%s\n' "$profiles" | grep -q "APN: '$EXPECTED_APN'"; then
        ubus call "network.interface.$MODEM_IF" down >/dev/null 2>&1 || true
        mmcli -m "$mid" --disable >/dev/null 2>&1 || true
        sleep 2
        if qmicli -d "$QMI_DEV" --device-open-proxy \
            --wds-modify-profile="3gpp,$PROFILE_ID,apn=$EXPECTED_APN,pdp-type=IPV4V6,auth=NONE" \
            >/dev/null 2>&1; then
            qmicli -d "$QMI_DEV" --device-open-proxy \
                --wds-set-lte-attach-pdn-list="$PROFILE_ID" >/dev/null 2>&1 || true
            log "restored configured LTE APN profile $PROFILE_ID"
        fi
    fi
fi

restart_tunnel
ubus call "network.interface.$MODEM_IF" down >/dev/null 2>&1 || true
sleep 3
ubus call "network.interface.$MODEM_IF" up >/dev/null 2>&1 ||
    ifup "$MODEM_IF" >/dev/null 2>&1 || true
if wait_real_lte; then
    restart_tunnel
    log 'LTE bearer recovered'
    exit 0
fi

log 'bearer reconnect failed; restarting modem remote processor only'
ubus call "network.interface.$MODEM_IF" down >/dev/null 2>&1 || true
/etc/init.d/modemmanager stop >/dev/null 2>&1 || true
sleep 2
if [ -w "$RPROC" ]; then
    printf 'stop\n' > "$RPROC" 2>/dev/null || true
    sleep 3
    printf 'start\n' > "$RPROC" 2>/dev/null || true
fi
sleep 8
/etc/init.d/modemmanager start >/dev/null 2>&1 || true
sleep 8
ubus call "network.interface.$MODEM_IF" up >/dev/null 2>&1 ||
    ifup "$MODEM_IF" >/dev/null 2>&1 || true
if wait_real_lte; then
    restart_tunnel
    log 'LTE recovered by modem-subsystem restart; host and Wi-Fi stayed up'
    exit 0
fi

log 'LTE remains offline; whole-device reboot deliberately suppressed'
exit 1
