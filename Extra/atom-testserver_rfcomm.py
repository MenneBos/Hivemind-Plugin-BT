#!/usr/bin/env python3
import bluetooth
import time
import subprocess

CHANNEL = 3

# --------------------------------------
#  get the RSSI
# --------------------------------------
def get_rssi(mac):
    """Vraag RSSI op via hcitool (werkt alleen als device verbonden is)."""
    try:
        output = subprocess.check_output(["hcitool", "rssi", mac], text=True)
        # output bv: "RSSI return value: -45"
        return int(output.strip().split()[-1])
    except Exception as e:
        print("Kon RSSI niet ophalen:", e)
        return None


def start_server():
    while True:
        print("[*] Wachten op verbinding van ESP32...")

        # RFCOMM server op kanaal 3
        server_sock = bluetooth.BluetoothSocket(bluetooth.RFCOMM)
        server_sock.bind(("", CHANNEL))
        server_sock.listen(1)

        try:
            client_sock, client_info = server_sock.accept()
            print(f"[+] Verbonden met ESP32: {client_info}")

            # heel kleine delay zodat Linux RSSI kan bepalen
            time.sleep(0.3)

            line = client_sock.recv(1024).decode().strip()  # ESP32 stuurt READY
            print(line)
           
            mac = client_info[0]
            # RSSI ophalen
            rssi = get_rssi(mac)
            print(rssi)
            if rssi is None:
                print("[-] Geen RSSI gevonden, gebruik 0")
                rssi = 0

            print(f"[TX] Stuur RSSI: {rssi}")

            # één lijn sturen, eindigend op '\n'
            client_sock.send(f"{rssi}\n".encode())

            # Python sluit de verbinding
            print("[*] Verbreek verbinding vanuit server")
            client_sock.close()

        except Exception as e:
            print("[-] Fout:", e)

        finally:
            server_sock.close()
            print("[*] Server reset — wacht op nieuwe connect...\n")
            time.sleep(0.3)


if __name__ == "__main__":
    start_server()