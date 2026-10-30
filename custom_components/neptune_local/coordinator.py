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
    PACKET_SYSTEM_STATE,
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

    def _log_raw(self, direction: str, data: bytes) -> None:
        if self._debug:
            _LOGGER.info("[Neptun %s] %s (%d bytes): %s",
                         self.host, direction, len(data), data.hex(" "))

    def _log_decoded(self, label: str, value: Any) -> None:
        if self._debug:
            _LOGGER.info("[Neptun %s]   %s = %r", self.host, label, value)

    def _connect(self) -> socket.socket:
        if self._debug:
            _LOGGER.info("[Neptun %s] Connecting to %s:%d (timeout=%ss)",
                         self.host, self.host, self.port, SOCKET_TIMEOUT)
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(SOCKET_TIMEOUT)
        sock.connect((self.host, self.port))
        return sock

    def _request(self, sock: socket.socket, packet: bytes) -> bytes:
        self._log_raw("TX", packet)
        sock.sendall(packet)
        raw = sock.recv(SOCKET_BUFSIZE)
        self._log_raw("RX", raw)
        return raw

    @staticmethod
    def _crc16(data: bytes) -> bytes:
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
        if len(payload) == 0:
            payload = b"\x00\x00"
        data = bytearray([2, 84, 81, packet_type]) + payload
        return bytes(data + cls._crc16(data))

    async def _async_update_data(self) -> dict[str, Any]:
        last_err: Exception | None = None
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
            except Exception as err:
                last_err = err
                _LOGGER.warning(
                    "[Neptun %s] Poll attempt %d/%d failed: %s",
                    self.host, attempt, RETRY_ATTEMPTS_PER_CYCLE, err,
                )
                if attempt < RETRY_ATTEMPTS_PER_CYCLE:
                    await asyncio.sleep(RETRY_DELAY)

        self._consecutive_failures += 1
        self._last_error = str(last_err)

        if self._consecutive_failures < MAX_CONSECUTIVE_FAILURES and self.data is not None:
            _LOGGER.warning(
                "[Neptun %s] Cycle %d/%d failed; keeping previous data. Entities stay available. Last error: %s",
                self.host, self._consecutive_failures, MAX_CONSECUTIVE_FAILURES, last_err,
            )
            return self.data

        raise UpdateFailed(
            f"[Neptun {self.host}] {self._consecutive_failures} consecutive "
            f"cycles failed. Last error: {last_err}"
        )

    def _sync_update(self) -> dict[str, Any]:
        sock = self._connect()
        try:
            device: dict[str, Any] = {"lines": {}}
            # Запрашиваем ТОЛЬКО 0x52 - он содержит все данные.
            raw = self._request(sock, self._build_packet(PACKET_SYSTEM_STATE))
            self._parse_system_state(raw, device)
            return device
        finally:
            sock.close()

    def _parse_system_state(self, data: bytes, device: dict[str, Any]) -> None:
        """Parse PACKET_SYSTEM_STATE (0x52)."""
        if len(data) < 8:
            self._log_decoded("system_state", "packet too short")
            return
            
        offset = 4
        payload_len = (data[offset] << 8) | data[offset + 1]
        offset += 2
        
        if payload_len == 0:
            self._log_decoded("system_state", "payload length is zero")
            return

        data_len = len(data) - 2
        while offset < data_len:
            tag = data[offset]
            offset += 1
            tag_size = (data[offset] << 8) | data[offset + 1]
            offset += 2

            # Проверка, чтобы не выйти за границы пакета
            if offset + tag_size > data_len:
                self._log_decoded(f"tag_0x{tag:02x}", "size exceeds packet length")
                break

            if tag == 0x49:  # Device Info (Name, MAC, Version)
                offset2 = offset
                name_size = tag_size
                device['device_name'] = data[offset2:offset2+name_size].decode('utf-8', errors='ignore')
                offset2 += name_size
                
                mac_size = (data[offset2] << 8) | data[offset2 + 1]
                offset2 += 2
                device['mac'] = data[offset2:offset2+mac_size].decode('utf-8', errors='ignore')
                offset2 += mac_size
                
                ver_size = (data[offset2] << 8) | data[offset2 + 1]
                offset2 += 2
                device['version'] = data[offset2:offset2+ver_size].decode('utf-8', errors='ignore')
                offset2 += ver_size
                
                offset = offset2  # Перескакиваем весь сложный тег
                self._log_decoded("device_info", f"{device['device_name']} / {device['mac']} / {device['version']}")
                continue

            elif tag == 0x53:  # Main State
                if tag_size >= 7:
                    device["valve_state_open"] = data[offset] == 1
                    device["sensor_count"] = data[offset + 1]
                    device["relay_count"] = data[offset + 2]
                    device["flag_dry"] = data[offset + 3] == 1
                    device["flag_cl_valve"] = data[offset + 4] == 1
                    device["line_in_config"] = data[offset + 5]
                    device["status"] = data[offset + 6]
                    device["status_name"] = self._decode_status(data[offset + 6])
                    
                    self._log_decoded("system.valve_state_open", device["valve_state_open"])
                    self._log_decoded("system.status_name", device["status_name"])

            elif tag == 0x73:  # Wired Lines
                for idx in range(min(4, tag_size)):
                    line = device["lines"].setdefault(f"line{idx}", {})
                    line["state"] = data[offset + idx]
                    line["wire"] = True
                    self._log_decoded(f"line{idx}.wired_state", line["state"])

            elif tag == 0x43:  # Counters (4 counters x 5 bytes)
                for idx in range(tag_size // 5):
                    line = device["lines"].setdefault(f"line{idx}", {})
                    val_off = offset + (idx * 5)
                    value = (
                        (data[val_off] << 24) | (data[val_off + 1] << 16) |
                        (data[val_off + 2] << 8) | data[val_off + 3]
                    )
                    line["value"] = value
                    line["step"] = data[val_off + 4]
                    line["type"] = "counter"
                    line["wire"] = True
                    self._log_decoded(f"line{idx}.counter", value)

            elif tag == 0x44:  # Counter Names
                name_str = data[offset:offset+tag_size].decode('utf-8', errors='ignore')
                device["counter_name"] = name_str
                self._log_decoded("counter_name", name_str)

            elif tag == 0x4c:
                # Какая-то служебная информация (возможно, реле)
                pass
            elif tag == 0x57:
                # Настройки
                pass
            else:
                self._log_decoded(f"unknown_tag_0x{tag:02x}", data[offset:offset+tag_size].hex(" "))

            offset += tag_size

    @staticmethod
    def _decode_status(status: int) -> str:
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
        await self._async_send_settings(valve_open=is_open)

    async def async_set_cleaning_mode(self, enabled: bool) -> None:
        await self._async_send_settings(cleaning=enabled)

    async def _async_send_settings(
        self,
        valve_open: bool | None = None,
        cleaning: bool | None = None,
    ) -> None:
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
        self._log_raw("TX (cmd)", packet)
        sock = self._connect()
        try:
            sock.sendall(packet)
        finally:
            sock.close()