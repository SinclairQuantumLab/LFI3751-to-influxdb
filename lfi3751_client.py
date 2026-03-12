"""
Simple RS-232 client for the Wavelength Electronics LFI-3751 temperature controller.

Typical use:
- Set the controller RS-232 address from the front panel.
- Connect the controller to the computer with RS-232 or USB-to-RS232.
- Use LFI3751Client in a with-block or call connect() / close() manually.
- Device info is queried automatically on connect().
- Use the helper methods for common reads.

This file also includes a small direct-run test at the bottom for quick debugging.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from types import TracebackType

import serial


class LFI3751Command(str, Enum):
    ACT_T = "01"
    ACT_R = "02"
    SET_T = "03"
    SET_R = "04"
    TE_I = "05"
    TE_V = "06"
    AUX_T = "09"

    RUN_STOP = "51"
    LOCAL = "53"
    PASSWORD = "54"
    SERIAL_NUMBER = "55"
    FIRMWARE_VERSION = "56"
    MODEL_NUMBER = "57"


class LFI3751Error(RuntimeError):
    """Raised when the controller returns a bad reply or nonzero end code."""

    def __init__(self, end_code: str, raw_reply: str) -> None:
        self.end_code: str = end_code
        self.raw_reply: str = raw_reply
        super().__init__(f"LFI-3751 command failed with end code {end_code}: {raw_reply}")


@dataclass(frozen=True)
class LFI3751Response:
    """Parsed response packet."""
    unit_type: str
    unit_number: str
    command_type: str
    command_code: str
    end_code: str
    data: str
    fcs: str
    raw_packet: str


class LFI3751Client:
    """Small client for talking to the LFI-3751 over RS-232."""

    def __init__(
        self,
        port: str,
        unit_number: str = "01",
        baudrate: int = 19200,
        timeout: float = 2.0,
    ) -> None:
        """Store connection settings."""
        self._port: str = port
        self._unit_number: str = f"{int(unit_number):02d}"
        self._baudrate: int = baudrate
        self._timeout: float = timeout

        self._ser: serial.Serial | None = None
        self._model: str | None = None
        self._version: str | None = None
        self._serial_number: str | None = None

    @property
    def port(self) -> str: """Serial port name."""; return self._port
    @property
    def unit_number(self) -> str: """LFI-3751 RS-232 unit number."""; return self._unit_number
    @property
    def baudrate(self) -> int: """Serial baudrate."""; return self._baudrate
    @property
    def timeout(self) -> float: """Serial timeout in seconds."""; return self._timeout
    @property
    def ser(self) -> serial.Serial | None: """Underlying serial object."""; return self._ser
    @property
    def model(self) -> str | None: """Device model string."""; return self._model
    @property
    def version(self) -> str | None: """Firmware version string."""; return self._version
    @property
    def serial_number(self) -> str | None: """Device serial number string."""; return self._serial_number

    def __enter__(self) -> "LFI3751Client":
        """Connect and return the client."""
        self.connect()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Close the connection on exit."""
        self.close()

    def __str__(self) -> str:
        """Return a short summary of the client and connected device."""
        if self._model is None and self._version is None and self._serial_number is None:
            return (
                f"LFI3751Client(port={self._port}, unit_number={self._unit_number}, "
                f"connected={self._ser is not None})"
            )

        return (
            f"LFI3751Client(model={self._model}, version={self._version}, "
            f"serial_number={self._serial_number}, port={self._port}, "
            f"unit_number={self._unit_number}, connected={self._ser is not None})"
        )

    def connect(self) -> None:
        """Open the serial connection and read device info."""
        if self._ser is not None:
            return

        self._ser = serial.Serial(
            port=self._port,
            baudrate=self._baudrate,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=self._timeout,
            xonxoff=True,
        )

        try:
            self._serial_number = self.get_serial_number()
            self._version = self.get_version()
            self._model = self.get_model()
        except Exception:
            self.close()
            raise

    def close(self) -> None:
        """Close the serial connection and clear cached device info."""
        if self._ser is not None:
            self._ser.close()
            self._ser = None

        self._model = None
        self._version = None
        self._serial_number = None

    def _calc_fcs(self, packet_without_fcs: str) -> str:
        """Calculate the two-character uppercase hex XOR checksum."""
        fcs = 0
        for ch in packet_without_fcs:
            fcs ^= ord(ch)
        return f"{fcs:02X}"

    def _build_packet(self, command_type: str, command_code: str, data: str) -> str:
        """Build one command packet."""
        if command_type not in ("1", "2"):
            raise ValueError(f"Invalid command_type: {command_type}")

        if len(command_code) != 2 or not command_code.isdigit():
            raise ValueError(f"Invalid command_code: {command_code}")

        if len(data) != 8:
            raise ValueError(f"Data field must be exactly 8 characters, got: {data!r}")

        packet_without_fcs = f"!1{self._unit_number}{command_type}{command_code}{data}"
        return packet_without_fcs + self._calc_fcs(packet_without_fcs)

    def _extract_packet(self, raw_reply: str) -> str:
        """Extract the first response packet starting with '@'."""
        for line in raw_reply.splitlines():
            line = line.strip()
            if line.startswith("@"):
                return line[:19]

        idx = raw_reply.find("@")
        if idx >= 0 and len(raw_reply) >= idx + 19:
            return raw_reply[idx:idx + 19]

        raise LFI3751Error("NO_REPLY", raw_reply)

    def _parse_response(self, raw_reply: str) -> LFI3751Response:
        """Parse and validate one response packet."""
        packet = self._extract_packet(raw_reply)

        if len(packet) != 19:
            raise LFI3751Error("BAD_REPLY", raw_reply)

        if packet[0] != "@":
            raise LFI3751Error("BAD_REPLY", raw_reply)

        packet_without_fcs = packet[:-2]
        packet_fcs = packet[-2:].upper()
        expected_fcs = self._calc_fcs(packet_without_fcs)

        if packet_fcs != expected_fcs:
            raise LFI3751Error("BAD_FCS", raw_reply)

        response = LFI3751Response(
            unit_type=packet[1],
            unit_number=packet[2:4],
            command_type=packet[4],
            command_code=packet[5:7],
            end_code=packet[7:9],
            data=packet[9:17],
            fcs=packet[17:19],
            raw_packet=packet,
        )

        if response.end_code != "00":
            raise LFI3751Error(response.end_code, raw_reply)

        return response

    def send_raw(self, packet: str) -> str:
        """Send one raw command packet and return the raw reply."""
        if self._ser is None:
            raise RuntimeError("Not connected. Call connect() first.")

        self._ser.reset_input_buffer()
        self._ser.write(packet.encode("ascii"))
        self._ser.flush()

        raw_reply = self._ser.read_until(b"\n").decode("ascii", errors="replace")
        if not raw_reply:
            raise LFI3751Error("NO_REPLY", raw_reply)

        return raw_reply

    def send_command(
        self,
        command: LFI3751Command,
        command_type: str,
        data: str = "+000.000",
    ) -> LFI3751Response:
        """Build, send, and parse one command."""
        packet = self._build_packet(command_type=command_type, command_code=command.value, data=data)
        raw_reply = self.send_raw(packet)
        return self._parse_response(raw_reply)

    def read_numeric(self, command: LFI3751Command) -> float:
        """Read one numeric value."""
        response = self.send_command(command, command_type="1", data="+000.000")
        return float(response.data)

    def write_numeric(self, command: LFI3751Command, value: float) -> float:
        """Write one numeric value and return the echoed/interpreted value."""
        response = self.send_command(command, command_type="2", data=f"{value:+08.3f}")
        return float(response.data)

    def read_text(self, command: LFI3751Command) -> str:
        """Read one 8-character text field."""
        response = self.send_command(command, command_type="1", data="+000.000")
        return response.data.strip()

    def write_text(self, command: LFI3751Command, data: str) -> str:
        """Write one 8-character text field and return the echoed text."""
        if len(data) != 8:
            raise ValueError("Text data must be exactly 8 characters.")
        response = self.send_command(command, command_type="2", data=data)
        return response.data

    def get_temperature_setpoint_C(self) -> float:
        """Read the temperature setpoint in degC."""
        return self.read_numeric(LFI3751Command.SET_T)

    def get_actual_temperature_C(self) -> float:
        """Read actual temperature in degC."""
        return self.read_numeric(LFI3751Command.ACT_T)

    def get_actual_resistance_kOhm(self) -> float:
        """Read actual sensor resistance in kOhm."""
        return self.read_numeric(LFI3751Command.ACT_R)

    def get_te_current_A(self) -> float:
        """Read thermoelectric current in amps."""
        return self.read_numeric(LFI3751Command.TE_I)

    def get_te_voltage_V(self) -> float:
        """Read thermoelectric voltage in volts."""
        return self.read_numeric(LFI3751Command.TE_V)

    def get_aux_temperature_C(self) -> float:
        """Read auxiliary sensor temperature in degC."""
        return self.read_numeric(LFI3751Command.AUX_T)

    def get_serial_number(self) -> str:
        """Read the instrument serial number."""
        return self.read_text(LFI3751Command.SERIAL_NUMBER)

    def get_version(self) -> str:
        """Read the firmware version."""
        return self.read_text(LFI3751Command.FIRMWARE_VERSION)

    def get_model(self) -> str:
        """Read the model number."""
        return self.read_text(LFI3751Command.MODEL_NUMBER)

    def set_temperature_setpoint_C(self, temperature_C: float) -> float:
        """Write the temperature setpoint in degC."""
        return self.write_numeric(LFI3751Command.SET_T, temperature_C)

    def go_local(self) -> None:
        """Return control to the front panel."""
        self.send_command(LFI3751Command.LOCAL, command_type="2", data="+000.000")


if __name__ == "__main__":
    """Run a simple connection test from the terminal."""
    import argparse

    def parse_args() -> argparse.Namespace:
        """Parse command-line arguments."""
        parser = argparse.ArgumentParser(
            description="Simple RS-232 client for the Wavelength Electronics LFI-3751."
        )
        parser.add_argument(
            "--port",
            type=str,
            default="/dev/ttyUSB0",
            help="Serial port. Defaults to /dev/ttyUSB0.",
        )
        parser.add_argument(
            "--unit-number",
            type=str,
            default="01",
            help="LFI-3751 RS-232 unit number. Defaults to 01.",
        )
        return parser.parse_args()

    args = parse_args()

    port = input(f"Serial port [if blank, {args.port}]: ").strip() or args.port
    unit_number = input(f"Unit number [if blank, {args.unit_number}]: ").strip() or args.unit_number

    print()

    with LFI3751Client(port=port, unit_number=unit_number) as client:
        print(client)
        print()

        temperature_C = client.get_actual_temperature_C()
        print("Actual temperature [degC]:", temperature_C)

        serial_number = client.get_serial_number()
        print("Serial number:", serial_number)

        version = client.get_version()
        print("Firmware version:", version)

        model = client.get_model()
        print("Model:", model)