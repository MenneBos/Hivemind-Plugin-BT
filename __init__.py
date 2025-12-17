#--------------------------
# deze werkt goed op de hivemind-staellite
# de esp32 code is main_minimal_rssi.cpp of
# M5_BT_min_rssi.ino
#--------------------------

import bluetooth
import threading
import subprocess

from ovos_plugin_manager.phal import PHALPlugin   # due to hivemind fakebus
from ovos_bus_client.message import Message       # due to hivemind fakebus
from ovos_utils.log import LOG

global server_sock

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

class AtomBTPlugin(PHALPlugin):
    def __init__(self, bus=None, config=None):
        super().__init__(bus=bus, name="atom_bt-phal-plugin", config=config)
        self.bus = bus
        LOG.info("AtomBTPlugin initialized")
        
        """Main loop: accept connections and process audio data."""       
        # Maak een RFCOMM server socket
        server_sock = bluetooth.BluetoothSocket(bluetooth.RFCOMM)
        server_sock.bind(("", CHANNEL))   
        server_sock.listen(1)
        LOG.info(f"RFCOMM server active on channel {CHANNEL}, waiting for ESP32...")

        # Start the Bluetooth server in a separate thread
        self.server_thread = threading.Thread(target=self.bt_server_loop) ## , daemon=True)
        self.server_thread.start()

    def bt_server_loop(self):

        try:
            while True:
                client_sock, client_info = server_sock.accept()
                LOG.info(f"Connected to: {client_info}")
                mac = client_info[0]

                data = client_sock.recv(1024)
                if not data:
                    break
                buffer += data.decode()

                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    cmd = line.strip()
                    print("Ontvangen:", cmd)

                    if cmd == "handler_rssi":
                        rssi = get_rssi(mac)
                        if rssi is not None:
                            msg = f"RSSI:{rssi}\n"
                        else:
                            msg = "RSSI:-999\n"
                        client_sock.send(msg.encode())
                        print("Verstuurd:", msg.strip())

                    elif cmd == "handler_audio_start":
                        pcm_buffer = io.BytesIO()
                        total_bytes = 0 

                        # Lees data zolang verbinding actief is
                        try:
                            while True:
                                data = client_sock.recv(1024)
                                if not data:
                                    break

                            pcm_buffer.write(data)
                            total_bytes += len(data)

                        except Exception as e:
                            print("Connection error:", e)

                        finally:
                            if client_sock:
                                client_sock.close()
                                #print("🔁 closed sockestarting to wait for next ESP32 connection...\n")
                                print(f"Correctly closed client, received {total_bytes} bytes")
                        
                        transcript = transcribe_with_chromium(pcm_buffer.getvalue())
                        print("🗣️ STT Result:", transcript)   
                    
                    elif cmd == "handler_audio_close":
                        print("Verbinding gesloten")
                        client_sock.close()
                        break   # <<< uitstappen uit de while-loop

        except Exception as e:
            LOG.info("Server error:", e)

        finally:
            if client_sock:
                client_sock.close()
            if server_sock:
                server_sock.close()
            LOG.info("Verbinding gesloten")
