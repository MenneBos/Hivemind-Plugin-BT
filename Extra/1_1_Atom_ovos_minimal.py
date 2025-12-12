import bluetooth

# Maak een RFCOMM server socket
server_sock = bluetooth.BluetoothSocket(bluetooth.RFCOMM)
server_sock.bind(("", 1))   # channel 1
server_sock.listen(1)

print("Wachten op verbinding...")
client_sock, client_info = server_sock.accept()
print("Verbonden met:", client_info)

try:
    while True:
        data = client_sock.recv(1024)
        if not data:
            break
        print("Ontvangen:", data.decode())
        client_sock.send(b"Hallo ESP32\n")
except OSError:
    pass

print("Verbinding gesloten")
client_sock.close()
server_sock.close()
