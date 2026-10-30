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
    CONF_RETRY_ATTEMPTS,
    CONF_RETRY_DELAY,
    CONF_MAX_CONSECUTIVE_FAILURES,
    DEFAULT_PORT,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_DEBUG,
    DEFAULT_RETRY_ATTEMPTS,
    DEFAULT_RETRY_DELAY,
    DEFAULT_MAX_CONSECUTIVE_FAILURES,
    PACKET_SYSTEM_STATE,
    SOCKET_BUFSIZE,
    SOCKET_TIMEOUT,
)

_LOGGER = logging.getLogger(__name__)


class NeptunCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator to manage fetching Neptun data."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the coordinator."""
        self.host = entry.data[CONF_HOST]
        self.port = DEFAULT_PORT
        self.scan_interval = entry.options.get(
            CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
        )
        self._debug = entry.options.get(CONF_DEBUG, DEFAULT_DEBUG)
        # Retry settings from options, falling back to defaults
        self._retry_attempts = entry.options.get(
            CONF_RETRY_ATTEMPTS, DEFAULT_RETRY_ATTEMPTS
        )
        self._retry_delay = entry.options.get(CONF_RETRY_DELAY, DEFAULT_RETRY_DELAY)
        self._max_consecutive_failures = entry.options.get(
            CONF_MAX_CONSECUTIVE_FAILURES, DEFAULT_MAX_CONSECUTIVE_FAILURES
        )
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
            _LOGGER.info(
                "[Neptun %s] %s (%d bytes): %s",
                self.host,
                direction,
                len(data),
                data.hex(" "),
            )

    def _log_decoded(self, label: str, value: Any) -> None:
        if self._debug:
            _LOGGER.info("[Neptun %s] %s = %r", self.host, label, value)

    def _connect(self) -> socket.socket:
        if self._debug:
            _LOGGER.info(
                "[Neptun %s] Connecting to %s:%d (timeout=%ss)",
                self.host,
                self.host,
                self.port,
                SOCKET_TIMEOUT,
            )
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

    @staticmethod
    def _crc16_check(data: bytes) -> bool:
        if len(data) < 2:
            return False
        expected = NeptunCoordinator._crc16(data[:-2])
        return data[-2:] == expected

    @classmethod
    def _build_packet(cls, packet_type: int, payload: bytes = b"") -> bytes:
        if len(payload) == 0:
            payload = b"\x00\x00"
        data = bytearray([2, 84, 81, packet_type]) + payload
        return bytes(data + cls._crc16(data))

    async def _async_update_data(self) -> dict[str, Any]:
        last_err: Exception | None = None

        for attempt in range(1, self._retry_attempts + 1):
            try:
                data = await asyncio.to_thread(self._sync_update)

                if self._consecutive_failures:
                    _LOGGER.info(
                        "[Neptun %s] Connection restored after %d failed cycle(s)",
                        self.host,
                        self._consecutive_failures,
                    )

                self._consecutive_failures = 0
                self._last_error = None
                return data

            except Exception as err:
                last_err = err
                _LOGGER.warning(
                    "[Neptun %s] Poll attempt %d/%d failed: %s",
                    self.host,
                    attempt,
                    self._retry_attempts,
                    err,
                )

                if attempt < self._retry_attempts:
                    await asyncio.sleep(self._retry_delay)

        self._consecutive_failures += 1
        self._last_error = str(last_err)

        if (
            self._consecutive_failures < self._max_consecutive_failures
            and self.data is not None
        ):
            _LOGGER.warning(
                "[Neptun %s] Cycle %d/%d failed; keeping previous data. "
                "Entities stay available. Last error: %s",
                self.host,
                self._consecutive_failures,
                self._max_consecutive_failures,
                last_err,
            )
            return self.data

        raise UpdateFailed(
            f"[Neptun {self.host}] "
            f"{self._consecutive_failures} consecutive "
            f"cycles failed. Last error: {last_err}"
        )

    def _sync_update(self) -> dict[str, Any]:
        sock = self._connect()
        try:
            device: dict[str, Any] = {"lines": {}}
            raw = self._request(
                sock,
                self._build_packet(PACKET_SYSTEM_STATE),
            )
            self._parse_system_state(raw, device)
            return device
        finally:
            sock.close()

    def _parse_system_state(
        self,
        data: bytes,
        device: dict[str, Any],
    ) -> None:
        """Parse PACKET_SYSTEM_STATE (0x52).

        Формат пакета:
          02 54 41 52 <len_hi> <len_lo> <tag> <tag_size_hi> <tag_size_lo> ...
        """
        if len(data) < 8:
            raise ValueError("system_state packet too short")

        if not self._crc16_check(data):
            raise ValueError("system_state packet has invalid CRC")

        if data[3] != PACKET_SYSTEM_STATE:
            raise ValueError(
                f"unexpected packet type 0x{data[3]:02x}, "
                f"expected 0x{PACKET_SYSTEM_STATE:02x}"
            )

        offset = 4
        payload_len = (data[offset] << 8) | data[offset + 1]
        offset += 2

        if payload_len == 0:
            self._log_decoded("system_state", "payload length is zero")
            return

        data_len = len(data) - 2
        payload_end = min(data_len, offset + payload_len)

        while offset < payload_end:
            if offset + 3 > payload_end:
                self._log_decoded("system_state", "truncated tag header")
                break

            tag = data[offset]
            tag_size = (data[offset + 1] << 8) | data[offset + 2]
            offset += 3

            tag_end = offset + tag_size
            if tag_end > payload_end:
                self._log_decoded(
                    f"tag_0x{tag:02x}",
                    "size exceeds packet length",
                )
                break

            payload = data[offset:tag_end]

            if tag == 0x49:
                # В оригинальном neptun.py тег 0x49 — это:
                #   2 байта типа устройства + 3 байта версии.
                # Например: 4E 33 32 32 30 -> "N3" / "2.2.0".
                if len(payload) >= 5:
                    device["device_type"] = payload[:2].decode(
                        "ascii", errors="ignore"
                    )
                    # Байты версии передаются как ASCII-символы (0x32 = '2')
                    device["version"] = (
                        f"{payload[2] - 0x30}.{payload[3] - 0x30}.{payload[4] - 0x30}"
                    )
                    self._log_decoded(
                        "device_info",
                        f"{device['device_type']} / {device['version']}",
                    )
                else:
                    self._log_decoded("tag_0x49", "payload too short")

            elif tag == 0x4E:
                # Имя устройства.
                device["device_name"] = payload.decode(
                    "utf-8", errors="ignore"
                ).rstrip("\x00")
                self._log_decoded("device_name", device["device_name"])

            elif tag == 0x4D:
                # MAC-адрес.
                device["mac"] = payload.decode(
                    "ascii", errors="ignore"
                ).rstrip("\x00")
                self._log_decoded("mac", device["mac"])

            elif tag == 0x41:
                # Разрешение локального управления.
                device["access"] = bool(payload[0]) if payload else False
                self._log_decoded("access", device["access"])

            elif tag == 0x53:
                # Основное состояние.
                if len(payload) >= 7:
                    device["valve_state_open"] = payload[0] == 1
                    device["sensor_count"] = payload[1]
                    device["relay_count"] = payload[2]
                    device["flag_dry"] = payload[3] == 1
                    device["flag_cl_valve"] = payload[4] == 1
                    device["line_in_config"] = payload[5]
                    device["status"] = payload[6]
                    device["status_name"] = self._decode_status(payload[6])

                    self._log_decoded(
                        "system.valve_state_open",
                        device["valve_state_open"],
                    )
                    self._log_decoded(
                        "system.status_name",
                        device["status_name"],
                    )
                else:
                    self._log_decoded("tag_0x53", "payload too short")

            elif tag == 0x73:
                # Состояния проводных линий.
                for idx, state in enumerate(payload[:4]):
                    line = device["lines"].setdefault(f"line{idx}", {})
                    line["state"] = state
                    line["wire"] = True
                    self._log_decoded(f"line{idx}.wired_state", state)

            elif tag == 0x43:
                # Показания счётчиков: 4 счётчика по 5 байт.
                for idx in range(len(payload) // 5):
                    val_off = idx * 5
                    value = (
                        (payload[val_off] << 24)
                        | (payload[val_off + 1] << 16)
                        | (payload[val_off + 2] << 8)
                        | payload[val_off + 3]
                    )
                    line = device["lines"].setdefault(f"line{idx}", {})
                    line["value"] = value
                    line["step"] = payload[val_off + 4]
                    line["type"] = "counter"
                    line["wire"] = True
                    self._log_decoded(f"line{idx}.counter", value)

            elif tag == 0x44:
                # Имена счётчиков.
                name_str = payload.decode(
                    "utf-8", errors="ignore"
                ).rstrip("\x00")
                device["counter_name"] = name_str
                self._log_decoded("counter_name", name_str)

            elif tag in (0x4C, 0x57):
                # Служебные теги, пока не используются.
                pass

            else:
                self._log_decoded(
                    f"unknown_tag_0x{tag:02x}",
                    payload.hex(" "),
                )

            offset = tag_end

    @staticmethod
    def _decode_status(status: int) -> str:
        if status == 0x00:
            return "NORMAL"

        parts: list[str] = []
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

        valve = (
            valve_open
            if valve_open is not None
            else current.get("valve_state_open", False)
        )
        dry = (
            cleaning
            if cleaning is not None
            else current.get("flag_dry", False)
        )
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