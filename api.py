# This file is part of the carrier_send_shipments_nacex module for Tryton.
# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
from trytond.model import fields
from trytond.pool import PoolMeta
from trytond.pyson import Eval, Not, Equal
from trytond.i18n import gettext
from trytond.exceptions import UserError
from .utils import nacex_call

__all__ = ['CarrierApi']


class CarrierApi(metaclass=PoolMeta):
    __name__ = 'carrier.api'
    nacex_delegacion = fields.Char('Delegacion',
        states={
            'required': Eval('method') == 'nacex',
        }, depends=['method'])
    nacex_abonado = fields.Char('Abonado',
        states={
            'required': Eval('method') == 'nacex',
        }, depends=['method'])
    nacex_hora_ini1 = fields.Char('hora_ini1')
    nacex_hora_fin1 = fields.Char('hora_fin1')
    nacex_hora_ini2 = fields.Char('hora_ini2')
    nacex_hora_fin2 = fields.Char('hora_fin2')
    nacex_envalse = fields.Selection([
        ('0', 'Docs'),
        ('1', 'Bag'),
        ('2', 'Pag'),
        ('D', 'Documents'),
        ('M', 'Muestras'),
        ], 'Envalse')
    nacex_print = fields.Selection([
        ('TECSV4_B', 'TECSV4'),
        ('TECFV4_B', 'TECFV4'),
        ('ZEBRA_B', 'ZEBRA'),
        ('IMAGEN_B', 'IMAGEN'),
        ], 'Print')

    @staticmethod
    def default_nacex_envalse():
        return '2'

    @staticmethod
    def default_nacex_print():
        return 'IMAGEN_B'

    @classmethod
    def get_carrier_app(cls):
        'Add Carrier Nacex APP'
        res = super(CarrierApi, cls).get_carrier_app()
        res.append(('nacex', 'Nacex'))
        return res

    @classmethod
    def view_attributes(cls):
        return super(CarrierApi, cls).view_attributes() + [
            ('//page[@id="nacex"]', 'states', {
                    'invisible': Not(Equal(Eval('method'), 'nacex')),
                    })]

    @classmethod
    def test_nacex(cls, api):
        'Test Nacex connection'
        resp = nacex_call(api, 'getAgencia', '08200')
        raise UserError(gettext(
                'carrier_send_shipments_nacex.msg_nacex_test_connection',
                message=resp.text))
