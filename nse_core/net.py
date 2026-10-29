"""HTTPS with certificate checks always on. Uses certifi's CA bundle when it's installed.

On macOS, Python from python.org ships without CA certificates: run "Install Certificates.command" in its
Applications folder, or `pip install certifi`. Verification is never switched off.
"""
from __future__ import annotations

import ssl
import urllib.error
import urllib.request

try:
    import certifi
    _CONTEXT = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    _CONTEXT = ssl.create_default_context()

HINT = ("Python can't verify HTTPS certificates. On macOS run 'Install Certificates.command' from your Python's "
        "Applications folder, or `pip install certifi`.")


def urlopen(req, timeout: float = 15):
    try:
        return urllib.request.urlopen(req, timeout=timeout, context=_CONTEXT)
    except urllib.error.URLError as e:
        if isinstance(e.reason, ssl.SSLCertVerificationError):
            raise urllib.error.URLError(HINT) from None
        raise
