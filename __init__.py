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

        # Blokkeer hier zodat het proces niet afsluit
        #self.server_thread.join()

    def bt_server_loop(self):
        """Main loop: accept connections and process audio data."""       
        # Maak een RFCOMM server socket
        server_sock = bluetooth.BluetoothSocket(bluetooth.RFCOMM)
        server_sock.bind(("", 1))   # channel 1
        server_sock.listen(1)

        LOG.info(f"RFCOMM server active on channel {CHANNEL}, waiting for ESP32...")
        client_sock, client_info = server_sock.accept()
        LOG.info(f"RFCOMM connected to: {client_info}")

        try:
            while True:
                data = client_sock.recv(1024)
                if not data:
                    break
                LOG.info(f"Ontvangen: {data.decode()}")
                client_sock.send(b"Hallo ESP32\n")
        except OSError:
            pass

        LOG.info("Verbinding gesloten")
        client_sock.close()
        server_sock.close()
