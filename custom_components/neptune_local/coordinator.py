"""Data update coordinator for Neptun Local."""

from __future__ import annotations

import asyncio
import logging
import socket
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    DOMAIN,
    CONF_HOST,
    CONF_SCAN_INTERVAL,
    DEFAULT_PORT,
    DEFAULT_SCAN_INTERVAL,
    PACKET_BACK_STATE,
    PACKET_SYSTEM_STATE,
    PACKET_SENSOR_STATE,
    PACKET_COUNTER_STATE,
    SERVER_PORT,
    SOCKET_BUFSIZE,
)

_LOGGER = logging.getLogger(__name__)


class NeptunCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator to manage fetching Neptun data."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the coordinator."""
        self.host = entry.data[CONF_HOST]
        self.port = DEFAULT_PORT
        self.scan_interval = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        self._socket: socket.socket | None = None

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=self.scan_interval),
        )

    def _connect(self) -> socket.socket:
        """Create and connect a TCP socket to the Neptun controller."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(10)
        sock.connect((self.host, self.port))
        return sock

    def _send_command(self, sock: socket.socket, data: bytes) -> None:
        """Send a raw command over the socket."""
        sock.sendall(data)

    def _recv_response(self, sock: socket.socket) -> bytes:
        """Receive a response from the socket."""
        return sock.recv(SOCKET_BUFSIZE)

    @staticmethod
    def _crc16(data: bytes) -> bytes:
        """Calculate CRC16 as used by the Neptun protocol[reference:3]."""
        crc = 0xFFFF
        for byte in data:
            crc ^= byte << 8
            crc &= 0xFFFF
            for _ in range(8):
                if crc & 0x8000:
                    crc = ((crc << 1) ^ 0x1021) & 0xFFFF
                else:
                    crc = (crc << 1) & 0xFFFF
        return bytes([(crc >> 8) & 0xFF, crc & 0xFF])

    @classmethod
    def _build_packet(cls, packet_type: int, payload: bytes = b"") -> bytes:
        """Build a packet with header, type, payload and CRC."""
        data = bytearray([2, 84, 81, packet_type]) + payload
        return bytes(data + cls._crc16(data))

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from the Neptun controller."""
        try:
            return await asyncio.to_thread(self._sync_update)
        except Exception as err:
            raise UpdateFailed(f"Error communicating with Neptun: {err}") from err

    def _sync_update(self) -> dict[str, Any]:
        """Synchronous update routine executed in a thread."""
        sock = self._connect()
        try:
            device: dict[str, Any] = {"lines": {}}

            # 1. Request system state (contains main valve, flags, wired lines)[reference:4]
            sock.sendall(self._build_packet(PACKET_SYSTEM_STATE))
            raw = self._recv_response(sock)
            self._parse_system_state(raw, device)

            # 2. Request background status (alarm flags)[reference:5]
            sock.sendall(self._build_packet(PACKET_BACK_STATE))
            raw = self._recv_response(sock)
            self._parse_background_status(raw, device)

            # 3. Request wireless sensor states[reference:6]
            sock.sendall(self._build_packet(PACKET_SENSOR_STATE))
            raw = self._recv_response(sock)
            self._parse_sensor_state(raw, device)

            # 4. Request counter values (if any)[reference:7]
            sock.sendall(self._build_packet(PACKET_COUNTER_STATE))
            raw = self._recv_response(sock)
            self._parse_counter_state(raw, device)

            return device
        finally:
            sock.close()

    def _parse_system_state(self, data: bytes, device: dict[str, Any]) -> None:
        """Parse PACKET_SYSTEM_STATE (0x52)[reference:8]."""
        if len(data) < 10:
            return
        offset = 6
        data_len = len(data) - 2
        while offset < data_len:
            tag = data[offset]
            offset += 1
            tag_size = (data[offset] << 8) | data[offset + 1]
            offset += 2
            offset2 = offset
            if tag == 0x53:  # Main state block
                device["valve_state_open"] = data[offset2] == 1
                offset2 += 1
                device["sensor_count"] = data[offset2]
                offset2 += 1
                device["relay_count"] = data[offset2]
                offset2 += 1
                device["flag_dry"] = data[offset2] == 1
                offset2 += 1
                device["flag_cl_valve"] = data[offset2] == 1
                offset2 += 1
                device["line_in_config"] = data[offset2]
                offset2 += 1
                device["status"] = data[offset2]
                device["status_name"] = self._decode_status(data[offset2])
            elif tag == 0x73:  # Wired lines state
                for idx in range(4):
                    line = device["lines"].setdefault(f"line{idx}", {})
                    line["state"] = data[offset2 + idx]
            offset += tag_size

    def _parse_background_status(self, data: bytes, device: dict[str, Any]) -> None:
        """Parse PACKET_BACK_STATE (0x42)[reference:9]."""
        if len(data) < 8:
            return
        offset = 4
        tag_size = (data[offset] << 8) | data[offset + 1]
        offset += 2
        if tag_size > 0:
            device["status"] = data[offset]
            device["status_name"] = self._decode_status(data[offset])

    def _parse_sensor_state(self, data: bytes, device: dict[str, Any]) -> None:
        """Parse PACKET_SENSOR_STATE (0x53)[reference:10]."""
        if len(data) < 8:
            return
        offset = 6
        data_len = len(data) - 2
        idx = 4
        while offset < data_len:
            line = device["lines"].setdefault(f"line{idx}", {})
            line["signal"] = data[offset]
            line["line"] = data[offset + 1]
            line["battery"] = data[offset + 2]
            line["state"] = data[offset + 3]
            line["wire"] = False
            offset += 4
            idx += 1

    def _parse_counter_state(self, data: bytes, device: dict[str, Any]) -> None:
        """Parse PACKET_COUNTER_STATE (0x43)[reference:11]."""
        if len(data) < 8:
            return
        offset = 6
        data_len = len(data) - 2
        idx = 0
        while offset < data_len:
            line = device["lines"].setdefault(f"line{idx}", {})
            # The original code has a potential bug in value calculation; we use a straightforward big-endian read
            value = (data[offset] << 24) | (data[offset + 1] << 16) | (data[offset + 2] << 8) | data[offset + 3]
            line["value"] = value
            line["step"] = data[offset + 4]
            line["type"] = "counter"
            line["wire"] = True
            offset += 5
            idx += 1

    @staticmethod
    def _decode_status(status: int) -> str:
        """Decode status bit mask to a string[reference:12]."""
        if status == 0x00:
            return "NORMAL"
        parts = []
        if status & 0x01:
            parts.append("ALARM")
        if status & 0x02:
            parts.append("MAIN BATTERY")
        if status & 0x04:
            parts.append("SENSOR BATTERY")
        if status & 0x08:
            parts.append("SENSOR OFFLINE")
        return ",".join(parts)

    async def async_set_valve(self, is_open: bool) -> None:
        """Open or close the main valve."""
        await self._async_send_settings(valve_open=is_open)

    async def async_set_cleaning_mode(self, enabled: bool) -> None:
        """Enable or disable the cleaning mode."""
        await self._async_send_settings(cleaning=enabled)

    async def _async_send_settings(
        self,
        valve_open: bool | None = None,
        cleaning: bool | None = None,
    ) -> None:
        """Send a settings packet to change valve or cleaning state[reference:13]."""
        current = self.data or {}
        valve = valve_open if valve_open is not None else current.get("valve_state_open", False)
        dry = cleaning if cleaning is not None else current.get("flag_dry", False)
        cl_valve = current.get("flag_cl_valve", False)
        line_config = current.get("line_in_config", 0)

        payload = bytearray([0, 7, 0x53, 0, 4, 0, 0, 0, 0])
        if valve:
            payload[5] = 1
        if dry:
            payload[6] = 1
        if cl_valve:
            payload[7] = 1
        payload[8] = line_config

        packet = self._build_packet(0x57, bytes(payload))
        await asyncio.to_thread(self._send_raw_packet, packet)

    def _send_raw_packet(self, packet: bytes) -> None:
        """Send a raw packet in a blocking thread."""
        sock = self._connect()
        try:
            sock.sendall(packet)
        finally:
            sock.close()