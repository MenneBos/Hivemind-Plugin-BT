#!/usr/bin/env python3
import os
import time
import subprocess
import serial

RFCOMM_CHANNEL = 3
RFCOMM_DEVICE = f"/dev/rfcomm{RFCOMM_CHANNEL}"
ESP32_MAC = "F0:24:F9:BC:EB:A2"  # Pas aan
BAUDRATE = 115200
SCAN_INTERVAL = 1  # seconden

def start_rfcomm_listener():
    """Start RFCOMM listener op kanaal 3"""
    print(f"[*] Start RFCOMM listener op kanaal {RFCOMM_CHANNEL}...")
    return subprocess.Popen(
        ["sudo", "rfcomm", "listen", str(RFCOMM_CHANNEL)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )

def is_esp32_connected(mac):
    """Check echte connectie via hcitool"""
    try:
        out = subprocess.check_output(["hcitool", "con"]).decode()
        return mac in out
    except subprocess.CalledProcessError:
        return False

def get_rssi(mac):
    """Meet RSSI via hcitool"""
    try:
        out = subprocess.check_output(["hcitool", "rssi", mac], stderr=subprocess.DEVNULL)
        return int(out.decode().strip().split()[-1])
    except Exception:
        return 0

def wait_for_device_ready():
    """Wacht tot ESP32 echt verbonden is en handshake READY stuurt"""
    print("[*] Wachten tot ESP32 verbonden en READY stuurt en klaar voor data...")
    
    while True:
        if os.path.exists(RFCOMM_DEVICE):
            try:
                ser = serial.Serial(RFCOMM_DEVICE, BAUDRATE, timeout=1)
                
                # Wacht op handshake byte van ESP32
                line = b""
                while b"\n" not in line:
                    c = ser.read(1)  # blokkeert max 1s door timeout=1
                    if c:
                        line += c
                print("[*] Handshake ontvangen:", line.decode().strip())
                
                return ser  # Nu is SPP ready, ser.write kan veilig
            except serial.SerialException:
                # Device bestaat maar nog niet open
                time.sleep(0.5)
        else:
            time.sleep(0.5)


def main():
    while True:
        listener = start_rfcomm_listener()
        ser = wait_for_device_ready()
        print("[*] ESP32 echt verbonden!")

        rssi = get_rssi(ESP32_MAC)
        print(f"[TX] Stuur RSSI: {rssi}")

        try:
            ser.write(f"{rssi}\n".encode())
        except Exception as e:
            print(f"[-] Fout bij verzenden: {e}")

        ser.close()
        listener.terminate()
        listener.wait()

        print("[*] Verbinding verbroken, wacht opnieuw...")
        time.sleep(SCAN_INTERVAL)

if __name__ == "__main__":
    main()
