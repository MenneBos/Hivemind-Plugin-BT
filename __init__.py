import io
import soundfile as sf
import requests
import json
import subprocess
import numpy as np
import bluetooth
import wave
import struct
import signal
import sys
import threading
from ovos_plugin_manager.phal import PHALPlugin   # due to hivemind fakebus
from ovos_bus_client.message import Message       # due to hivemind fakebus
from ovos_utils.log import LOG

# --------------------------------------
#  Gracefull stop server with CTRL-C
# --------------------------------------
CHUNK = 4096
CHROMIUM_STT_URL = "http://www.google.com/speech-api/v2/recognize"
API_KEY = "AIzaSyBOti4mM-6x9WDnZIjIeyEU21OpBXqWBgw"
LANG = "nl-NL"
PFILTER = 1
SAMPLE_RATE = 16000
SILENCE_THRESHOLD = 100  # adjust based on your mic amplitude
MAX_SILENT_CHUNKS = 20   # stop if 20 chunks in a row are silent
silent_count = 0
CHANNEL = 2
## Global references so the signal handler can close them
server_sock = None

# Path to your audio file
audio_file = "audio.raw"

# --------------------------------------
#  Convert PCM -> FLAC
# --------------------------------------
def pcm_to_flac(pcm_bytes, sample_rate=SAMPLE_RATE):
    audio_np = np.frombuffer(pcm_bytes, dtype=np.int16)
    audio_np_swapped = audio_np.byteswap().newbyteorder()

    flac_buffer = io.BytesIO()
    sf.write(flac_buffer, audio_np, samplerate=sample_rate, format='FLAC', subtype='PCM_16')
    flac_buffer.seek(0)

#    sf.write("audio.wav", audio_np.reshape(-1,1), samplerate=16000,
#         format="WAV", subtype="PCM_16")
#    subprocess.run(["aplay", "audio.wav"])

#    samples_be = np.frombuffer(pcm_bytes, dtype='>i2')  # big-endian
#    samples_le = np.frombuffer(pcm_bytes, dtype='<i2')  # little-endian
    
#    np.savetxt("audio.csv", samples_le, delimiter=",", fmt="%d")
#    np.savetxt("audio_swapped.csv", samples_be, delimiter=",", fmt="%d")
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
#  Gracefull stop server with CTRL-C
# --------------------------------------
def signal_handler(sig, frame):
    print("\nCtrl-C detected, shutting down gracefully...")
    if client_sock:
        try:
            client_sock.close()
            print("Client socket closed")
        except Exception:
            pass
    if server_sock:
        try:
            server_sock.close()
            print("Server socket closed")
        except Exception:
            pass
    if wav_file:
        try:
            wav_file.close()
            print("WAV file closed")
        except Exception:
            pass
    sys.exit(0)


signal.signal(signal.SIGINT, signal_handler)

# --------------------------------------
#  Automatic Gain Control (AGC)
# --------------------------------------
def simple_agc(samples, target=8000, strength=0.02):
    """
    A simple smooth AGC:
    - target: desired RMS amplitude
    - strength: AGC reaction speed (0.01–0.05 recommended)
    """
    rms = np.sqrt(np.mean(samples.astype(np.float32)**2))
    if rms < 1:
        return samples  # avoid division by zero & silence artifacts

    gain = 1.0 + strength * ((target / rms) - 1.0)

    # Apply gain safely with saturation
    samples = samples.astype(np.float32) * gain
    samples = np.clip(samples, -32768, 32767)

    return samples.astype(np.int16)

# --------------------------------------
#  OPTIONAL: High-pass filter (improves clarity)
# --------------------------------------
def high_pass_filter(samples, alpha=0.95):
    """
    Simple one-pole high-pass filter.
    Removes low-frequency rumble from PDM mics.
    """
    filtered = np.zeros_like(samples)
    prev = 0
    for i, x in enumerate(samples):
        filtered[i] = alpha * (filtered[i-1] if i > 0 else 0) + x - prev
        prev = x
    return filtered.astype(np.int16)

# --------------------------------------
#  Audio processing pipeline
# --------------------------------------
def process_audio_chunk(data):
    samples = np.frombuffer(data, dtype=np.int16)

    # Optional clarity improvement
    #samples = high_pass_filter(samples, alpha=0.97)

    # Apply AGC
    samples = simple_agc(samples, target=9000, strength=0.02)

    # Optional extra manual gain (fine-tune)
    #EXTRA_GAIN = 1.2  # +1.5 dB
    #samples = np.clip(samples * EXTRA_GAIN, -32768, 32767).astype(np.int16)

    return samples.tobytes()

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

# --------------------------------------
#  Main Bluetooth server loop
# --------------------------------------
class AtomBTPlugin(PHALPlugin):
    def __init__(self, bus=None, config=None):
        super().__init__(bus=bus, name="atom_bt-phal-plugin", config=config)
        self.bus = bus
        LOG.info("AtomBTPlugin initialized")

        # Start the Bluetooth server in a separate thread
        self.server_thread = threading.Thread(target=self.bt_server_loop) ## , daemon=True)
        self.server_thread.start()

        # Blokkeer hier zodat het proces niet afsluit
        self.server_thread.join()

    def bt_server_loop(self):
        """Main loop: accept connections and process audio data."""
        self.server_sock = bluetooth.BluetoothSocket(bluetooth.RFCOMM)
        self.server_sock.bind(("", CHANNEL))
        self.server_sock.listen(1)
        LOG.info(f"RFCOMM server active on channel {CHANNEL}, waiting for ESP32...")

        try:
            while True:
                client_sock, client_info = self.server_sock.accept()
                LOG.info(f"Connection established with {client_info}")

                mac = client_info[0]

                # Meet RSSI
                rssi = get_rssi(mac)
                if rssi is not None:
                    msg = f"RSSI:{rssi}\n"
                    client_sock.send(msg)
                    print("Verstuurd:", msg)

                pcm_buffer = io.BytesIO()
                total_bytes = 0

                try:
                    while True:
                        data = client_sock.recv(4096)
                        if not data:
                            break
                        
                        pcm_buffer.write(data)
                        total_bytes += len(data)

                except Exception as e:
                    LOG.error(f"Connection error: {e}")

                finally:
                    client_sock.close()
                    LOG.info("Client disconnected, waiting for next connection...")

                LOG.info(f"Closed client, received {total_bytes} bytes")

                # Replace with your STT function
                transcript = transcribe_with_chromium(pcm_buffer.getvalue())
                LOG.info(f"STT Result: {transcript}")

                # Emit to the OVOS bus
                if self.bus:
                    self.bus.emit(Message("recognizer_loop:utterance", {
                        "utterances": [transcript],
                        "lang": "nl-NL"
                    }))

        except Exception as e:
            LOG.error(f"Server error: {e}")

        finally:
            self.server_sock.close()