"""Render URLs as QR codes in a terminal."""

import sys


def print_terminal_qr(data, out=None):
    """Print a QR code and return whether rendering succeeded."""
    try:
        import qrcode
    except ImportError:
        return False

    output = sys.stdout if out is None else out
    try:
        qr = qrcode.QRCode(
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            border=4,
        )
        qr.add_data(data)
        qr.print_ascii(out=output, tty=output.isatty())
    except (OSError, ValueError, qrcode.exceptions.DataOverflowError):
        return False
    return True
