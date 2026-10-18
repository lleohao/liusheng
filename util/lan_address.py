"""Helpers for selecting a phone-reachable LAN address."""

import ipaddress
import socket


def _usable_ipv4(address):
    try:
        parsed = ipaddress.ip_address(address)
    except ValueError:
        return False
    return isinstance(parsed, ipaddress.IPv4Address) and not (
        parsed.is_loopback or parsed.is_unspecified
    )


def is_loopback_host(host):
    if host.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def lan_ipv4_address():
    """Return the likely LAN IPv4 address without sending network traffic."""
    probe = None
    try:
        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # UDP connect only selects a route; it sends no datagram. TEST-NET-1
        # avoids depending on DNS or a real external service.
        probe.connect(("192.0.2.1", 80))
        address = probe.getsockname()[0]
        if _usable_ipv4(address):
            return address
    except (OSError, TypeError, IndexError):
        pass
    finally:
        if probe is not None:
            try:
                probe.close()
            except OSError:
                pass

    try:
        addresses = socket.gethostbyname_ex(socket.gethostname())[2]
    except (OSError, TypeError, IndexError):
        return None
    return next((address for address in addresses if _usable_ipv4(address)), None)
