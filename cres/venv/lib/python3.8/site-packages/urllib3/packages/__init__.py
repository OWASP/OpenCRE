from __future__ import absolute_import

__all__ = ("ssl_match_hostname",)

try:
    # cPython >= 2.7.9 has ssl features backported from Python3
    from ssl import CertificateError
    del CertificateError
    import ssl as ssl_match_hostname
except ImportError:
    from . import ssl_match_hostname
