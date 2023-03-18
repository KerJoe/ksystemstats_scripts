#!/usr/bin/env bash

tab=$(printf '\t')
while :; do
    read query
    case "$query" in
        "?")
            echo "gpu_fan_rpm"
            ;;
        "gpu_fan_rpm${tab}value")
            value=$(nvidia-settings -q all | grep  -i "Attribute 'GPUCurrentFanSpeedRPM'" | cut -d : -f4 | cut -d . -f1 | cut -c2-)
            echo $value
            ;;
        "gpu_fan_rpm${tab}unit")
            echo "rpm"
            ;;
        *)
            echo
            ;;
    esac
done
