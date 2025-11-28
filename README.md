# Bluetooth Plugin
It setup up a BT scan server continously checking possible connection from an ESP32 Atom Echo. Once the Echo makes a connection PCM data will be transported to the plugin. The plugin will encode the PCM data to FLAC data and sends it to a STT service from Chromium. The text will be put on the Hivemind fakebus for further processing. 

Goal is to have a small handdevice to communicate with the OVOS services, directly or via Satellites. The Echo will select the closest speaker and reponses will can from the speaker from the hivemind satelitte of server.

Good conversational experience due to missing wakeword and a distance between the speaker and mic.







