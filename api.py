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
        })
    nacex_abonado = fields.Char('Abonado',
        states={
            'required': Eval('method') == 'nacex',
        })
    nacex_hora_ini1 = fields.Char('hora_ini1')
    nacex_hora_fin1 = fields.Char('hora_fin1')
    nacex_hora_ini2 = fields.Char('hora_ini2')
    nacex_hora_fin2 = fields.Char('hora_fin2')
    nacex_envase = fields.Selection([
        ('0', 'Docs'),
        ('1', 'Bag'),
        ('2', 'Pag'),
        ('D', 'Documents'),
        ('M', 'Muestras'),
        ], 'Envase')
    nacex_tip_ea = fields.Selection([
        ('N', 'Without ealerta'),
        ('S', 'Ealerta informed by SMS'),
        ('E', 'Ealerta informed by EMAIL'),
        ], 'Nacex Type eAlerta', sort=False)

    @classmethod
    def __setup__(cls):
        super(CarrierApi, cls).__setup__()
        nacex_print = [
            ('TECSV4_B', 'Nacex TECSV4'),
            ('TECFV4_B', 'Nacex TECFV4'),
            ('ZEBRA_B', 'Nacex ZEBRA'),
            ('IMAGEN_B', 'Nacex IMAGEN'),
            ]
        cls.print_report.selection.extend(nacex_print)

    @staticmethod
    def default_nacex_envase():
        return '2'

    @staticmethod
    def default_nacex_tip_ea():
        return 'N'

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
        data = {}
        data['cp'] = '08200'
        resp = nacex_call(api, 'getAgencia', data)
        raise UserError(gettext(
                'carrier_send_shipments_nacex.msg_nacex_test_connection',
                message=resp.text))
