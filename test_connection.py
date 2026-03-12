"""
Test connection to the Wavelength Electronics LFI-3751 temperature controller.

Set the controller RS-232 address  on the front panel first. This machine has its own addressing when daisy-chained; default is "01".
Then connect the controller to your computer using an RS-232 connection
(or a USB-to-RS232 adapter).

Change SERIAL_PORT below to match your system, for example:
- Windows: "COM3"
- Raspberry Pi / Linux: "/dev/ttyUSB0"
"""

import time
import serial


# --- settings ---

SERIAL_PORT = "/dev/ttyUSB0"   # change this to your serial port
UNIT_NUMBER = "01"             # RS-232 address set on the controller front panel


# --- helper: calculate FCS ---

def calc_fcs(packet_without_fcs: str) -> str:
    fcs = 0
    for ch in packet_without_fcs:
        fcs ^= ord(ch)
    return f"{fcs:02X}"


# --- connect ---

print("Connecting...")

ser = serial.Serial(
    port=SERIAL_PORT,
    baudrate=19200,
    bytesize=serial.EIGHTBITS,
    parity=serial.PARITY_NONE,
    stopbits=serial.STOPBITS_ONE,
    timeout=2,
    xonxoff=True,
)

print("Connected.\n")


# --- ask for serial number ---

packet = f"!1{UNIT_NUMBER}155+000.000"
packet += calc_fcs(packet)

print("Sending:", packet)
ser.write(packet.encode("ascii"))

reply = ser.read_until(b"\n").decode("ascii", errors="replace")
print("Reply:")
print(reply)
print()

time.sleep(0.2)


# --- ask for firmware version ---

packet = f"!1{UNIT_NUMBER}156+000.000"
packet += calc_fcs(packet)

print("Sending:", packet)
ser.write(packet.encode("ascii"))

reply = ser.read_until(b"\n").decode("ascii", errors="replace")
print("Reply:")
print(reply)
print()

time.sleep(0.2)


# --- ask for model number ---

packet = f"!1{UNIT_NUMBER}157+000.000"
packet += calc_fcs(packet)

print("Sending:", packet)
ser.write(packet.encode("ascii"))

reply = ser.read_until(b"\n").decode("ascii", errors="replace")
print("Reply:")
print(reply)
print()


# --- close connection ---

ser.close()

print("Connection closed.")