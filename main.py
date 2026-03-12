"""
Poll the LFI-3751 temperature controller and upload readings to InfluxDB.

This script runs continuously, polls the LFI-3751 at a fixed interval,
and uploads the latest temperature controller readings to InfluxDB.
On device communication failure, it re-establishes the connection once
and retries the query once. Other exceptions are allowed to raise so
supervisor can restart the process.
"""

from supervisor_helper import *
from lfi3751_client import LFI3751Client, LFI3751Error

import serial
import time


print()
print("----- Wavelength Electronics LFI-3751 temperature controller -> InfluxDB uploader -----")
print()

# >>> LFI-3751 connection >>>
SERIAL_PORT = "/dev/ttyUSB0"
UNIT_NUMBER = "01"
# <<< LFI-3751 connection <<<

# >>> loop configuration >>>
INTERVAL_s = 5
print(f"Polling interval = {INTERVAL_s} s.")
print()
# <<< loop configuration <<<

# >>> InfluxDB configuration >>>
import influxdb_client
from influxdb_client.client.write_api import SYNCHRONOUS
INFLUXDB_URL = "http://synology-nas:8086"
INFLUXDB_TOKEN = "xixuoRzjm51D2WQh5uHnqjd0H28NJuaKpiHAmmSzEUlqgUhxRl0A01Na6-a_gX6BENlP3xx8FEoGP-qMx0Xrow=="  # sinclairgroup_influxdb's admin token
INFLUXDB_ORG = "sinclairgroup"
INFLUXDB_BUCKET = "imaq"
INFLUXDB_CLIENT = influxdb_client.InfluxDBClient(url=INFLUXDB_URL, token=INFLUXDB_TOKEN, org=INFLUXDB_ORG)
INFLUXDB_WRITE_API = INFLUXDB_CLIENT.write_api(write_options=SYNCHRONOUS)
print(f"InfluxDB client initialized for org='{INFLUXDB_ORG}', bucket='{INFLUXDB_BUCKET}'.")
print()
# <<< InfluxDB configuration <<<


def connect_lfi3751() -> LFI3751Client:
    """Connect to the LFI-3751."""
    client = LFI3751Client(
        port=SERIAL_PORT,
        unit_number=UNIT_NUMBER,
    )
    client.connect()
    return client


print(f"Connecting to LFI-3751 on {SERIAL_PORT} (unit {UNIT_NUMBER})...", end=" ")
lfi3751_client = connect_lfi3751()
print("Done.")
print(lfi3751_client)
print()

il = 0

print("Entering main polling loop...")
print()

while True:
    msg_il = f"Iteration {il}: "

    try:
        temperature_set_C = lfi3751_client.get_temperature_setpoint_C()
        temperature_C = lfi3751_client.get_actual_temperature_C()
        current_A = lfi3751_client.get_te_current_A()
        voltage_V = lfi3751_client.get_te_voltage_V()

    except (serial.SerialException, OSError, LFI3751Error) as ex:
        log_error(msg_il)
        log_error(f"LFI-3751 query failed: {type(ex).__name__}: {ex}")
        log_warn("Re-establishing LFI-3751 connection and retrying once...")

        try:
            lfi3751_client.close()
        except Exception:
            pass

        lfi3751_client = connect_lfi3751()
        log_warn("LFI-3751 reconnection succeeded.")

        temperature_set_C = lfi3751_client.get_temperature_setpoint_C()
        temperature_C = lfi3751_client.get_actual_temperature_C()
        current_A = lfi3751_client.get_te_current_A()
        voltage_V = lfi3751_client.get_te_voltage_V()

    influxdb_record = {
        "measurement": "LFI3751_TemperatureController",
        "tags": {
            "SN": lfi3751_client.serial_number or "",
            "version": lfi3751_client.version or "",
            "source": "RS-232",
        },
        "fields": {
            "TemperatureSet[degC]": temperature_set_C,
            "Temperature[degC]": temperature_C,
            "Current[A]": current_A,
            "Voltage[V]": voltage_V,
        },
    }

    INFLUXDB_WRITE_API.write(
        bucket=INFLUXDB_BUCKET,
        org=INFLUXDB_ORG,
        record=influxdb_record,
    )

    log(
        msg_il
        + f"TemperatureSet[degC]={temperature_set_C:.3f}, "
        + f"Temperature[degC]={temperature_C:.3f}, "
        + f"Current[A]={current_A:.3f}, "
        + f"Voltage[V]={voltage_V:.3f}"
    )

    time.sleep(INTERVAL_s)
    il += 1