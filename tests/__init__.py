# This file is part of the carrier_send_shipments_nacex module for Tryton.
# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.

try:
    from trytond.modules.carrier_send_shipments_nacex.tests.test_carrier_send_shipments_nacex import suite
except ImportError:
    from .test_carrier_send_shipments_nacex import suite

__all__ = ['suite']
