import bluetooth
import threading


from ovos_plugin_manager.phal import PHALPlugin   # due to hivemind fakebus
from ovos_bus_client.message import Message       # due to hivemind fakebus
from ovos_utils.log import LOG

CHANNEL = 3

class AtomBTPlugin(PHALPlugin):
    def __init__(self, bus=None, config=None):
        super().__init__(bus=bus, name="atom_bt-phal-plugin", config=config)
        self.bus = bus
        LOG.info("AtomBTPlugin initialized")

        # Start the Bluetooth server in a separate thread
        self.server_thread = threading.Thread(target=self.bt_server_loop) ## , daemon=True)
        self.server_thread.start()

    def bt_server_loop(self):
        """Main loop: accept connections and process audio data."""       
        # Maak een RFCOMM server socket
        server_sock = bluetooth.BluetoothSocket(bluetooth.RFCOMM)
        server_sock.bind(("", 1))   # channel 1
        server_sock.listen(1)

        LOG.info(f"RFCOMM server active on channel {CHANNEL}, waiting for ESP32...")
        try:
            while True:
                client_sock, client_info = server_sock.accept()
                LOG.info(f"Connected to: {client_info}")

                try:
                    while True:
                        data = client_sock.recv(1024)
                        if not data:
                            break
                        print("Ontvangen:", data.decode())
                        client_sock.send(b"Hallo ESP32\n")
                except OSError:
                    pass

        except Exception as e:
            print("Server error:", e)

        finally:
            if client_sock:
                client_sock.close()
            if server_sock:
                server_sock.close()
            LOG.info("Verbinding gesloten")
