#!/bin/bash
# Installs or removes smoothd on the phone. Run as root from this folder.
#   ./install.sh          install and start (survives reboots and system updates)
#   ./install.sh remove   stop, restore stock values, remove everything it added
# Writes only /root/smoothd/ and /etc/systemd/system/smoothd.service, on the
# writable data partition; the read-only system image is untouched.
set -e
cd "$(dirname "$0")"
[ "$(id -u)" = 0 ] || { echo "run as root"; exit 1; }

if [ "$1" = remove ]; then
    systemctl disable --now smoothd.service 2>/dev/null || true   # stopping restores stock values
    rm -f /etc/systemd/system/smoothd.service
    rm -rf /root/smoothd
    systemctl daemon-reload
    echo "smoothd removed"
    exit 0
fi

install -d -m 700 /root/smoothd
install -m 644 smoothd.py /root/smoothd/smoothd.py
install -m 644 install.sh /root/smoothd/install.sh
install -m 644 smoothd.service /etc/systemd/system/smoothd.service
systemctl daemon-reload
systemctl enable smoothd.service
systemctl restart smoothd.service
sleep 3
systemctl --no-pager status smoothd.service | head -12
