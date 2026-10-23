from __future__ import annotations

import logging
import socket
import threading

logger = logging.getLogger(__name__)


def _lan_ipv4() -> str:
    """Return the IPv4 address used by the current default LAN route."""
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # UDP connect chooses an interface without sending application data.
        probe.connect(("8.8.8.8", 80))
        return probe.getsockname()[0]
    finally:
        probe.close()


class MdnsAdvertiser:
    """Advertise the FastAPI endpoint for ESP32 discovery on the local LAN."""

    service_type = "_mini-flood._tcp.local."

    def __init__(self, hostname: str, port: int, enabled: bool = True) -> None:
        self.hostname = hostname.removesuffix(".local")
        self.port = port
        self.enabled = enabled
        self._zeroconf = None
        self._service_info = None

    def start(self) -> bool:
        if not self.enabled:
            return False
        try:
            from zeroconf import ServiceInfo, Zeroconf
        except ImportError:
            logger.warning("mDNS disabled: install dependency 'zeroconf'")
            return False

        try:
            address = _lan_ipv4()
            server = f"{self.hostname}.local."
            self._service_info = ServiceInfo(
                type_=self.service_type,
                name=f"Mini Flood Backend.{self.service_type}",
                addresses=[socket.inet_aton(address)],
                port=self.port,
                properties={
                    b"api": b"/api/v2/telemetry",
                    b"version": b"2",
                },
                server=server,
            )
            # Chỉ bind card mạng đang mang default route để tránh adapter ảo
            # (VPN/Hyper-V/Bluetooth) làm mDNS chậm hoặc chọn sai địa chỉ.
            self._zeroconf = Zeroconf(interfaces=[address])
            self._zeroconf.register_service(
                self._service_info,
                allow_name_change=True,
            )
            logger.info(
                "mDNS advertised: %s.local -> %s:%d",
                self.hostname,
                address,
                self.port,
            )
            return True
        except Exception:
            logger.exception("Could not advertise Mini Flood backend through mDNS")
            self.stop()
            return False

    def run(self, stop_event: threading.Event, retry_seconds: float = 30.0) -> None:
        """Keep trying to advertise without blocking the API lifecycle.

        ``zeroconf.register_service`` can take several seconds or raise
        ``EventLoopBlocked`` on Windows when multicast is unavailable.  This
        method is intended to run in a daemon thread: a failed registration is
        retried after a bounded delay, while API startup and shutdown remain
        independent from the optional discovery service.
        """
        if not self.enabled:
            return

        try:
            while not stop_event.is_set():
                if self.start():
                    stop_event.wait()
                    break
                if stop_event.wait(max(0.1, retry_seconds)):
                    break
        finally:
            self.stop()

    def stop(self) -> None:
        zeroconf = self._zeroconf
        service_info = self._service_info
        self._zeroconf = None
        self._service_info = None
        if zeroconf is None:
            return
        try:
            if service_info is not None:
                zeroconf.unregister_service(service_info)
        except Exception:
            logger.warning("Could not unregister Mini Flood mDNS service", exc_info=True)
        try:
            zeroconf.close()
        except Exception:
            logger.warning("Could not close Mini Flood mDNS advertiser", exc_info=True)
