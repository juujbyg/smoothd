#!/bin/sh
# launch.sh APPID : start an app as phablet and return at once.
U=32011
timeout 5 su phablet -c "XDG_RUNTIME_DIR=/run/user/$U DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/$U/bus lomiri-app-launch $1" </dev/null >/dev/null 2>&1 &
