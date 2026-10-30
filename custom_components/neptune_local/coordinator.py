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
    CONF_DEBUG,
    DEFAULT_PORT,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_DEBUG,
    MAX_CONSECUTIVE_FAILURES,
    RETRY_ATTEMPTS_PER_CYCLE,
    RETRY_DELAY,
    SOCKET_TIMEOUT,
    PACKET_BACK_STATE,
    PACKET_SYSTEM_STATE,
    PACKET_SENSOR_STATE,
    PACKET_COUNTER_STATE,
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
        self._debug = entry.options.get(CONF_DEBUG, DEFAULT_DEBUG)
        self._consecutive_failures = 0
        self._last_error: str | None = None

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=self.scan_interval),
        )

    # ------------------------------------------------------------------ #
    # Debug helpers
    # ------------------------------------------------------------------ #
    def _log_raw(self, direction: str, data: bytes) -> None:
        """Log a raw packet in hex when debug is enabled."""
        if self._debug:
            _LOGGER.info("[Neptun %s] %s (%d bytes): %s",
                         self.host, direction, len(data), data.hex(" "))

    def _log_decoded(self, label: str, value: Any) -> None:
        """Log a decoded value when debug is enabled."""
        if self._debug:
            _LOGGER.info("[Neptun %s]   %s = %r", self.host, label, value)

    # ------------------------------------------------------------------ #
    # Socket layer
    # ------------------------------------------------------------------ #
    def _connect(self) -> socket.socket:
        """Create and connect a TCP socket to the Neptun controller."""
        if self._debug:
            _LOGGER.info("[Neptun %s] Connecting to %s:%d (timeout=%ss)",
                         self.host, self.host, self.port, SOCKET_TIMEOUT)
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(SOCKET_TIMEOUT)
        sock.connect((self.host, self.port))
        return sock

    def _request(self, sock: socket.socket, packet: bytes) -> bytes:
        """Send a packet and receive the response, logging both."""
        self._log_raw("TX", packet)
        sock.sendall(packet)
        raw = sock.recv(SOCKET_BUFSIZE)
        self._log_raw("RX", raw)
        return raw

    @staticmethod
    def _crc16(data: bytes) -> bytes:
        """Calculate CRC16 as used by the Neptun protocol."""
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

    # ------------------------------------------------------------------ #
    # Update pipeline
    # ------------------------------------------------------------------ #
    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from Neptun with retries and soft failure handling."""
        last_err: Exception | None = None

        # Intra-cycle retries
        for attempt in range(1, RETRY_ATTEMPTS_PER_CYCLE + 1):
            try:
                data = await asyncio.to_thread(self._sync_update)
                if self._consecutive_failures:
                    _LOGGER.info(
                        "[Neptun %s] Connection restored after %d failed cycle(s)",
                        self.host, self._consecutive_failures,
                    )
                self._consecutive_failures = 0
                self._last_error = None
                return data
            except Exception as err:  # noqa: BLE001
                last_err = err
                _LOGGER.warning(
                    "[Neptun %s] Poll attempt %d/%d failed: %s",
                    self.host, attempt, RETRY_ATTEMPTS_PER_CYCLE, err,
                )
                if attempt < RETRY_ATTEMPTS_PER_CYCLE:
                    await asyncio.sleep(RETRY_DELAY)

        # All attempts in this cycle failed
        self._consecutive_failures += 1
        self._last_error = str(last_err)

        if (
            self._consecutive_failures < MAX_CONSECUTIVE_FAILURES
            and self.data is not None
        ):
            _LOGGER.warning(
                "[Neptun %s] Cycle %d/%d failed; keeping previous data. "
                "Entities stay available. Last error: %s",
                self.host,
                self._consecutive_failures,
                MAX_CONSECUTIVE_FAILURES,
                last_err,
            )
            return self.data

        raise UpdateFailed(
            f"[Neptun {self.host}] {self._consecutive_failures} consecutive "
            f"cycles failed. Last error: {last_err}"
        )

    def _sync_update(self) -> dict[str, Any]:
        """Synchronous update routine executed in a worker thread."""
        sock = self._connect()
        try:
            device: dict[str, Any] = {"lines": {}}

            # 1. System state
            raw = self._request(sock, self._build_packet(PACKET_SYSTEM_STATE))
            self._parse_system_state(raw, device)

            # 2. Background status (alarms)
            raw = self._request(sock, self._build_packet(PACKET_BACK_STATE))
            self._parse_background_status(raw, device)

            # 3. Wireless sensors
            raw = self._request(sock, self._build_packet(PACKET_SENSOR_STATE))
            self._parse_sensor_state(raw, device)

            # 4. Counters
            raw = self._request(sock, self._build_packet(PACKET_COUNTER_STATE))
            self._parse_counter_state(raw, device)

            return device
        finally:
            sock.close()

    # ------------------------------------------------------------------ #
    # Parsers (each also logs decoded values in debug mode)
    # ------------------------------------------------------------------ #
    def _parse_system_state(self, data: bytes, device: dict[str, Any]) -> None:
        """Parse PACKET_SYSTEM_STATE (0x52)."""
        if len(data) < 10:
            self._log_decoded("system_state", "packet too short, ignored")
            return
        offset = 6
        data_len = len(data) - 2
        while offset < data_len:
            tag = data[offset]
            offset += 1
            tag_size = (data[offset] << 8) | data[offset + 1]
            offset += 2
            offset2 = offset
            if tag == 0x53:
                device["valve_state_open"] = data[offset2] == 1
                device["sensor_count"] = data[offset2 + 1]
                device["relay_count"] = data[offset2 + 2]
                device["flag_dry"] = data[offset2 + 3] == 1
                device["flag_cl_valve"] = data[offset2 + 4] == 1
                device["line_in_config"] = data[offset2 + 5]
                device["status"] = data[offset2 + 6]
                device["status_name"] = self._decode_status(data[offset2 + 6])

                self._log_decoded("system.valve_state_open", device["valve_state_open"])
                self._log_decoded("system.sensor_count", device["sensor_count"])
                self._log_decoded("system.relay_count", device["relay_count"])
                self._log_decoded("system.flag_dry", device["flag_dry"])
                self._log_decoded("system.flag_cl_valve", device["flag_cl_valve"])
                self._log_decoded("system.line_in_config", device["line_in_config"])
                self._log_decoded("system.status_name", device["status_name"])
            elif tag == 0x73:
                for idx in range(4):
                    line = device["lines"].setdefault(f"line{idx}", {})
                    line["state"] = data[offset2 + idx]
                    self._log_decoded(f"line{idx}.wired_state", line["state"])
            offset += tag_size

    def _parse_background_status(self, data: bytes, device: dict[str, Any]) -> None:
        """Parse PACKET_BACK_STATE (0x42)."""
        if len(data) < 8:
            self._log_decoded("background_status", "packet too short, ignored")
            return
        offset = 4
        tag_size = (data[offset] << 8) | data[offset + 1]
        offset += 2
        if tag_size > 0:
            device["status"] = data[offset]
            device["status_name"] = self._decode_status(data[offset])
            self._log_decoded("background.status_name", device["status_name"])

    def _parse_sensor_state(self, data: bytes, device: dict[str, Any]) -> None:
        """Parse PACKET_SENSOR_STATE (0x53)."""
        if len(data) < 8:
            self._log_decoded("sensor_state", "packet too short, ignored")
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

            self._log_decoded(f"line{idx}.signal", line["signal"])
            self._log_decoded(f"line{idx}.line", line["line"])
            self._log_decoded(f"line{idx}.battery", line["battery"])
            self._log_decoded(f"line{idx}.state", line["state"])

            offset += 4
            idx += 1

    def _parse_counter_state(self, data: bytes, device: dict[str, Any]) -> None:
        """Parse PACKET_COUNTER_STATE (0x43)."""
        if len(data) < 8:
            self._log_decoded("counter_state", "packet too short, ignored")
            return
        offset = 6
        data_len = len(data) - 2
        idx = 0
        while offset < data_len:
            line = device["lines"].setdefault(f"line{idx}", {})
            value = (
                (data[offset] << 24)
                | (data[offset + 1] << 16)
                | (data[offset + 2] << 8)
                | data[offset + 3]
            )
            line["value"] = value
            line["step"] = data[offset + 4]
            line["type"] = "counter"
            line["wire"] = True

            self._log_decoded(f"line{idx}.counter_value", value)
            self._log_decoded(f"line{idx}.counter_step", line["step"])

            offset += 5
            idx += 1

    @staticmethod
    def _decode_status(status: int) -> str:
        """Decode status bit mask to a string."""
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

    # ------------------------------------------------------------------ #
    # Outgoing commands
    # ------------------------------------------------------------------ #
    async def async_set_valve(self, is_open: bool) -> None:
        """Open or close the main valve."""
        await self._async_send_settings(valve_open=is_open)

    async def async_set_cleaning_mode(self, enabled: bool) -> None:
        """Enable or disable cleaning mode."""
        await self._async_send_settings(cleaning=enabled)

    async def _async_send_settings(
        self,
        valve_open: bool | None = None,
        cleaning: bool | None = None,
    ) -> None:
        """Send a settings packet to change valve or cleaning state."""
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
        self._log_raw("TX (cmd)", packet)
        sock = self._connect()
        try:
            sock.sendall(packet)
        finally:
            sock.close()