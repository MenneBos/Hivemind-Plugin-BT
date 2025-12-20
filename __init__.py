#--------------------------
# deze werkt goed op de hivemind-staellite
# de esp32 code is main_minimal_rssi.cpp of
# M5_BT_min_rssi.ino
#--------------------------

import bluetooth
import threading
import subprocess
import numpy as np
import soundfile as sf
import io
import signal
import sys
import requests
import json
import time

from ovos_plugin_manager.phal import PHALPlugin   # due to hivemind fakebus
from ovos_bus_client.message import Message       # due to hivemind fakebus
from ovos_utils.log import LOG

#=========== variables =====================
CHUNK = 4096
CHROMIUM_STT_URL = "http://www.google.com/speech-api/v2/recognize"
API_KEY = "AIzaSyBOti4mM-6x9WDnZIjIeyEU21OpBXqWBgw"
LANG = "nl-NL"
PFILTER = 1
SAMPLE_RATE = 16000
SILENCE_THRESHOLD = 100  # adjust based on your mic amplitude
MAX_SILENT_CHUNKS = 20   # stop if 20 chunks in a row are silent
silent_count = 0
CHANNEL = 3
## Global references so the signal handler can close them
server_sock = None
client_sock = None
# Path to your audio file
audio_file = "audio.raw"
FirstTime = True
HANDLER_LEN = 19  # vaste lengte van de handler
AUDIO_CHUNK = 120

bus = Message()
#bus.run_in_thread()   # important
#bus.wait_for_ready()

# --------------------------------------
#  Convert PCM -> FLAC
# --------------------------------------
def pcm_to_flac(pcm_bytes, sample_rate=SAMPLE_RATE):
    # Zorg dat buffer een veelvoud van 2 bytes is (PCM16)
    if len(pcm_bytes) % 2 != 0:
        pcm_bytes = pcm_bytes[:-1]

    audio_np = np.frombuffer(pcm_bytes, dtype=np.int16)
    audio_np_swapped = audio_np.byteswap().newbyteorder()

    flac_buffer = io.BytesIO()
    sf.write(flac_buffer, audio_np, samplerate=sample_rate, format='FLAC', subtype='PCM_16')
    flac_buffer.seek(0)

    #sf.write("audio.wav", audio_np.reshape(-1,1), samplerate=16000,
    #     format="WAV", subtype="PCM_16")
    #subprocess.run(["aplay", "audio.wav"])

    return flac_buffer.read()

# --------------------------------------
#  Send FLAC -> Chromium STT
# --------------------------------------
def transcribe_with_chromium(pcm_data, sample_rate=SAMPLE_RATE):
    flac_data = pcm_to_flac(pcm_data, sample_rate)
    params = {
        "client": "chromium",
        "lang": LANG,
        "key": API_KEY,
        "pFilter": PFILTER
    }
    headers = {"Content-Type": f"audio/x-flac; rate={sample_rate}"}
    response = requests.post(CHROMIUM_STT_URL, headers=headers, data=flac_data, params=params)
    if response.ok:
        # Chromium returns multiple JSON blobs separated by newlines
        for line in response.text.strip().splitlines():
            if line.strip().startswith('{'):
                result = json.loads(line)
                if result.get("result"):
                    alt = result["result"][0]["alternative"][0]
                    return alt["transcript"]
                
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
        self.buffer = ""
        LOG.info("AtomBTPlugin initialized")
        
        """Main loop: accept connections and process audio data."""       
        # Maak een RFCOMM server socket
        self.server_sock = bluetooth.BluetoothSocket(bluetooth.RFCOMM)
        self.server_sock.bind(("", CHANNEL))   
        self.server_sock.listen(1)
        LOG.info(f"RFCOMM server active on channel {CHANNEL}, waiting for ESP32...")

        # Start the Bluetooth server in a separate thread
        self.server_thread = threading.Thread(target=self.bt_server_loop) ## , daemon=True)
        self.server_thread.start()

    def bt_server_loop(self):
        try:
            while True:
                self.client_sock, self.client_info = self.server_sock.accept()
                self.client_sock.settimeout(0.2)

                LOG.info(f"Connected to: {self.client_info}")
                self.mac = self.client_info[0]

                audio_active = False
                pcm_buffer = io.BytesIO()
                total_bytes = 0

                while True:
                    try:
                        data = self.client_sock.recv(AUDIO_CHUNK)
                    except socket.timeout:
                        continue

                    if not data:
                        break

                    # ---- handler detectie ----
                    if len(data) == HANDLER_LEN:
                        cmd = data.decode("utf-8", errors="ignore").strip("\0").strip()
                        LOG.info(f"Handler received: {cmd}")

                        if cmd == "handler_rssi":
                            rssi = get_rssi(self.mac)
                            msg = f"RSSI:{rssi if rssi is not None else -999}\n"
                            self.client_sock.send(msg.encode())

                        elif cmd == "handler_audio_start":
                            pcm_buffer = io.BytesIO()
                            total_bytes = 0
                            audio_active = True
                            LOG.info("🎙 audio start")

                        elif cmd == "handler_audio_close":
                            LOG.info("⏹ audio stop")
                            audio_active = False
                            break

                        continue  # handler verwerkt

                    # ---- audio data ----
                    if audio_active:
                        pcm_buffer.write(data)
                        total_bytes += len(data)

                # ---- na audio ----
                if total_bytes > 0:
                    LOG.info(f"Received {total_bytes} bytes audio")
                    transcript = transcribe_with_chromium(pcm_buffer.getvalue())
                    LOG.info(f"🗣 STT Result: {transcript}")
                    self.bus.emit(
                        "ovos.plugin.audio.transcript",
                        {"transcript": transcript}
                    )

                self.client_sock.close()
                LOG.info("Client socket closed, waiting for next ESP32")

        except Exception as e:
            LOG.error(f"Server error: {e}")

        finally:
            if self.client_sock:
                self.client_sock.close()
            if self.server_sock:
                self.server_sock.close()
