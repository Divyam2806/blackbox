#!/bin/bash
# Host-HAL SIL Build Script
g++ -I./hal_shim hal_shim/sil_main.cpp firmware_samples/cooling_fan_buggy/src/main.ino -o sil_fan_runner
echo "[+] Built sil_fan_runner successfully"
