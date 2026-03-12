"""
Pytest connection test for the Wavelength Electronics LFI-3751 temperature controller.

Set the controller RS-232 address on the front panel first.
For a single controller, use address 01.

Then connect the controller to your computer using an RS-232 connection
(or a USB-to-RS232 adapter).

Change SERIAL_PORT below to match your system, for example:
- Windows: "COM3"
- Raspberry Pi / Linux: "/dev/ttyUSB0"

Run with:
    pytest -s test_connection.py
"""

import time

import pytest
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


# --- helper: build packet ---

def make_read_packet(command_code: str) -> str:
    packet = f"!1{UNIT_NUMBER}1{command_code}+000.000"
    packet += calc_fcs(packet)
    return packet


# --- helper: send one command and read one reply ---

def send_and_read(ser: serial.Serial, command_code: str) -> str:
    packet = make_read_packet(command_code)

    print("Sending:", packet)
    ser.write(packet.encode("ascii"))

    reply = ser.read_until(b"\n").decode("ascii", errors="replace")

    print("Reply:")
    print(reply)
    print()

    return reply


@pytest.fixture(scope="module")
def ser():
    print("Connecting...")

    try:
        s = serial.Serial(
            port=SERIAL_PORT,
            baudrate=19200,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=2,
            xonxoff=True,
        )
    except Exception as e:
        pytest.skip(f"Could not open serial port {SERIAL_PORT}: {e}")

    print("Connected.\n")

    yield s

    s.close()
    print("Connection closed.")


def test_read_serial_number(ser):
    reply = send_and_read(ser, "55")
    assert reply.startswith("@")
    assert len(reply.strip()) > 0
    time.sleep(0.2)


def test_read_firmware_version(ser):
    reply = send_and_read(ser, "56")
    assert reply.startswith("@")
    assert len(reply.strip()) > 0
    time.sleep(0.2)


def test_read_model_number(ser):
    reply = send_and_read(ser, "57")
    assert reply.startswith("@")
    assert "LFI-3751" in reply
    time.sleep(0.2)