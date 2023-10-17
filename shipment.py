# This file is part of the carrier_send_shipments module for Tryton.
# The COPYRIGHT file at the top level of this repository contains
# the full copyright notices and license terms.
import logging
import tempfile
import base64
from trytond.pool import Pool, PoolMeta
from trytond.model import ModelSQL, ModelView, fields
from trytond.transaction import Transaction
from trytond.i18n import gettext
from trytond.exceptions import UserError
from trytond.modules.carrier_send_shipments.tools import unaccent, unspaces
from .utils import nacex_call

__all__ = ['ShipmentOut']

logger = logging.getLogger(__name__)


class NacexMixin(ModelSQL, ModelView):
    nacex_envase = fields.Selection('get_nacex_envase', 'Nacex Envase')
    nacex_set_pickup_address = fields.Boolean('Nacex Set Pickup Address',
        help="NACEX: Set to true, if the warehouse address is differnet from "
            "the one setted in Nacex register as pickup.")
    nacex_tip_ea = fields.Selection([
        (None, ''),
        ('N', 'Without ealerta'),
        ('S', 'Ealerta informed by SMS'),
        ('E', 'Ealerta informed by EMAIL'),
        ], 'Nacex Type eAlerta', sort=False)
    nacex_ealerta = fields.Char('Nacex eAlerta')
    nacex_frec_codigo = fields.Selection([
        (None, ''),
        ('1', 'Interdia or Puente Urbano: morning'),
        ('2', 'Interdia or Puente Urbano: late'),
        ('8', 'Puente urbano night'),
        ('9', 'Interdia aerial'),
        ], 'Nacex Freq Codigo', sort=False)
    nacex_ret = fields.Selection([
        ('N', 'N'),
        ('S', 'S'),
        ], 'Nacex Ret', sort=False)
    nacex_ref_cli = fields.Char('Nacex Ref Cli')

    @staticmethod
    def get_nacex_envase():
        Api = Pool().get('carrier.api')
        selection = Api.fields_get(
            ['nacex_envase'])['nacex_envase']['selection']
        return [(None, '')] + selection

    @staticmethod
    def default_nacex_envase():
        return None

    @staticmethod
    def default_nacex_set_pickup_address():
        return False

    @staticmethod
    def default_nacex_tip_ea():
        return None

    @staticmethod
    def default_nacex_frec_codigo():
        return None

    @staticmethod
    def default_nacex_ret():
        return 'N'

    @fields.depends('nacex_tip_ea', 'customer')
    def on_change_nacex_tip_ea(self):
        if self.nacex_tip_ea == 'S':
            self.nacex_ealerta = self.customer.mobile
        if self.nacex_tip_ea == 'E':
            self.nacex_ealerta = self.customer.email

    @classmethod
    def nacex_label_file(cls, api, dbname, agencia, numero, api_label):
        if api.print_report == 'IMAGEN_B':
            try:
                content = base64.urlsafe_b64decode(
                    api_label + '=' * (4 - len(api_label) % 4))
            except TypeError:
                return
            suffix = '.png'
        else:
            try:
                content = api_label.encode()
            except AttributeError:
                return
            suffix = None

        with tempfile.NamedTemporaryFile(
                prefix='%s-nacex-%s-%s-' % (dbname, agencia, numero),
                suffix=suffix, delete=False) as temp:
            temp.write(content)
        temp.close()
        return temp.name

class ShipmentOut(NacexMixin, metaclass=PoolMeta):
    __name__ = 'stock.shipment.out'

    @classmethod
    def send_nacex(cls, api, shipments):
        '''
        Send shipments out to nacex
        :param api: obj
        :param shipments: list
        Return references, labels, errors
        '''
        pool = Pool()
        CarrierApi = pool.get('carrier.api')
        ShipmentOut = pool.get('stock.shipment.out')
        Uom = pool.get('product.uom')
        Date = pool.get('ir.date')

        references = []
        labels = []
        errors = []

        default_service = CarrierApi.get_default_carrier_service(api)

        for shipment in shipments:
            service = (shipment.carrier_service or shipment.carrier.service or
                default_service)
            if not service:
                message = gettext(
                    'carrier_send_shipments_nacex.msg_nacex_add_services')
                errors.append(message)
                continue

            if api.reference_origin and hasattr(shipment, 'origin'):
                code = (shipment.origin and shipment.origin.rec_name or
                    shipment.number)
            else:
                code = shipment.number

            packages = shipment.number_packages
            if not packages or packages == 0:
                packages = 1

            weight = 1
            if api.weight and hasattr(shipment, 'manual_weight'):
                weight = shipment.manual_weight or shipment.weight
                if not weight:
                    weight = 1

                if api.weight_api_unit:
                    if shipment.weight_uom:
                        weight = Uom.compute_qty(
                            shipment.weight_uom, weight, api.weight_api_unit)
                    elif api.weight_unit:
                        weight = Uom.compute_qty(
                            api.weight_unit, weight, api.weight_api_unit)

                # weight must integer value, not float
                weight = int(round(weight))
                weight = 1 if weight == 0 else weight

            if shipment.warehouse.address:
                waddress = shipment.warehouse.address
            else:
                waddresses = api.company.party.addresses
                if not waddresses:
                    raise UserError(gettext(
                            'carrier_send_shipments_nacex.'
                            'msg_missing_warehouse_address'))
                waddress = waddresses[0]

            data = {}
            data['del_cli'] = api.nacex_delegacion[:4]
            data['num_cli'] = api.nacex_abonado[:5]
            data['fec'] = Date.today().strftime("%d/%m/%Y")
            data['tip_ser'] = service.code
            # TODO: Tipo de cobro
            #   'O', Origen: Factura la agencia origen del envío
            #   'D', Destino: Factura la agencia de entrega del envío
            #   'T': Tercera: Factura una tercera agencia
            data['tip_cob'] = 'O'
            data['ref_cli'] = shipment.nacex_ref_cli and shipment.nacex_ref_cli[:20] or code[:20]
            data['tip_env'] = shipment.nacex_envase or api.nacex_envase or '2'
            data['bul'] = str(packages)[:3].zfill(3)
            data['kil'] = str(weight)
            data['nacex_ret'] = shipment.nacex_ret or 'N'

            # 1	Interdia or Puente Urbano: frequency 1 (morning)
            # 2	Interdia or Puente Urbano: frequency 2 (late)
            # 8	Puente urbano night.
            # 9	Interdía aerial.
            if shipment.nacex_frec_codigo:
                data['frec_codigo'] = shipment.nacex_frec_codigo

            # N	Without ealerta.
            # S	Ealerta informed by SMS.
            # E	Ealerta informed by EMAIL.
            data['tip_ea'] = shipment.nacex_tip_ea or 'N'
            if shipment.nacex_tip_ea == 'S' and shipment.nacex_ealerta:
                data['ealerta'] = shipment.nacex_ealerta
            elif shipment.nacex_tip_ea == 'E' and shipment.nacex_ealerta:
                data['ealerta'] = shipment.nacex_ealerta

            if shipment.nacex_set_pickup_address:
                data['dir_rec'] = unaccent(waddress.street.replace('\n', ' - ')
                    )[:60].rstrip()
                data['cp_rec'] = unaccent(waddress.postal_code)[:8]
                data['pob_rec'] = unaccent(waddress.city)[:30]
                data['pais_rec'] = unaccent(waddress.country and
                    waddress.country.code or '')
                data['tel_rec'] = unspaces(api.phone or
                    shipment.company.party.phone or '')[:35]
            data['nom_ent'] = unaccent(shipment.customer.name)[:35]
            data['per_ent'] = unaccent((shipment.delivery_address.party_name
                    or shipment.customer.name))[:35]
            data['dir_ent'] = unaccent(
                shipment.delivery_address.street.replace('\n', ' - ')
                )[:60].rstrip()
            data['cp_ent'] = unaccent(
                shipment.delivery_address.postal_code)[:15]
            data['pob_ent'] = unaccent(shipment.delivery_address.city)[:40]
            data['pais_ent'] = unaccent(shipment.delivery_address.country
                and shipment.delivery_address.country.code or '')
            data['tel_ent'] = unspaces(shipment.customer.mobile or
                shipment.customer.phone or '')[:15]
            if shipment.carrier_notes:
                data['obs1'] = unaccent(shipment.carrier_notes)[:38].rstrip()

            resp = nacex_call(api, 'putExpedicion', data)
            values = resp.text.split('|')

            if len(values) == 1 or resp.status_code != 200:
                message = gettext(
                    'carrier_send_shipments_nacex.msg_nacex_connection_error',
                    name=shipment.rec_name,
                    error=resp.text)
                errors.append(message)
                continue

            if values[0] == 'ERROR':
                message = gettext(
                    'carrier_send_shipments_nacex.msg_nacex_not_send_error',
                    name=shipment.rec_name,
                    error=resp.text)
                errors.append(message)
                continue

            # response example:
            # resp = codExp|agencia/numero expedicion|color|ruta|codigo agencia|nombre agencia|telf entrega|service|hora entrega|barcode|fecha prevista
            # resp = '9999999|2841/9999999|GRIS|2V|0832|VILAFRANCA|938902108|NACEX 19:00H|Entregar antes de las 19:00H.|00128419999999083208|07/05/2021|'

            reference = values[1]

            if reference:
                cls.write([shipment], {
                    'carrier_tracking_ref': reference,
                    'carrier_service': service,
                    'carrier_delivery': True,
                    'carrier_send_date': ShipmentOut.get_carrier_date(),
                    'carrier_send_employee': (
                        ShipmentOut.get_carrier_employee() or None),
                    })
                logger.info('Send shipment %s' % (shipment.number))
                references.append(shipment.number)
            else:
                logger.error('Not send shipment %s.' % (shipment.number))

            labels += cls.print_labels_nacex(api, [shipment])
        if labels:
            cls.write(shipments, {'carrier_printed': True})

        return references, labels, errors

    @classmethod
    def print_labels_nacex(cls, api, shipments):
        '''
        Get labels from shipments out from Nacex
        '''
        labels = []
        dbname = Transaction().database.name

        to_write = []
        for shipment in shipments:
            reference = shipment.carrier_tracking_ref
            if not reference:
                continue

            try:
                agencia, numero = reference.split('/')
            except ValueError:
                continue

            data = {}
            data['agencia'] = agencia
            data['numero'] = numero
            data['modelo'] = api.print_report

            resp = nacex_call(api, 'getEtiqueta', data)
            values = resp.text.split('|')

            if resp.status_code != 200 or values[0] == 'ERROR':
                continue

            api_label = resp.text
            temp_name = cls.nacex_label_file(api, dbname, agencia, numero, api_label)
            if not temp_name:
                continue
            labels.append(temp_name)

            to_write.extend(([shipment], {
                'carrier_printed': True,
                'carrier_tracking_label': fields.Binary.cast(
                    open(temp_name, "rb").read()),
                }))
        if to_write:
            cls.write(*to_write)
        return labels

    @classmethod
    def get_labels_nacex(cls, api, shipments):
        binary_label = []
        for label in cls.print_labels_nacex(api, shipments):
            binary_label.append(fields.Binary.cast(open(label, "rb").read()))
        return binary_label


class ShipmentOutReturn(NacexMixin, metaclass=PoolMeta):
    __name__ = 'stock.shipment.out.return'

    @classmethod
    def send_nacex(cls, api, shipments):
        '''
        Send shipments out return to nacex
        :param api: obj
        :param shipments: list
        Return references, labels, errors
        '''
        pool = Pool()
        ShipmentOutReturn = pool.get('stock.shipment.out.return')
        Uom = pool.get('product.uom')
        Date = pool.get('ir.date')
        Employee = pool.get('company.employee')

        references = []
        labels = []
        errors = []

        dbname = Transaction().database.name

        for shipment in shipments:
            if api.reference_origin and hasattr(shipment, 'origin'):
                code = (shipment.origin and shipment.origin.rec_name or
                    shipment.number)
            else:
                code = shipment.number

            packages = shipment.number_packages
            if not packages or packages == 0:
                packages = 1

            weight = 1
            if api.weight and hasattr(shipment, 'manual_weight'):
                weight = shipment.manual_weight or shipment.weight
                weight = 1 if weight == 0.0 else weight

                if api.weight_api_unit:
                    if shipment.weight_uom:
                        weight = Uom.compute_qty(
                            shipment.weight_uom, weight, api.weight_api_unit)
                    elif api.weight_unit:
                        weight = Uom.compute_qty(
                            api.weight_unit, weight, api.weight_api_unit)

                # weight is integer value, not float
                weight = int(round(weight))
                weight = 1 if weight == 0 else weight

            if shipment.warehouse.address:
                waddress = shipment.warehouse.address
            else:
                waddresses = api.company.party.addresses
                if not waddresses:
                    raise UserError(gettext(
                            'carrier_send_shipments_nacex.'
                            'msg_missing_warehouse_address'))
                waddress = waddresses[0]

            data = {}
            data['del_cli'] = api.nacex_delegacion[:4]
            data['num_cli'] = api.nacex_abonado[:5]

            data['nom_rem'] = unaccent(shipment.customer.name)[:35]
            data['fec'] = Date.today().strftime("%d/%m/%Y")
            data['ref_cli'] = code[:20]
            data['nom_ent'] = unaccent(api.company.party.name)[:50]
            employee_id = ShipmentOutReturn.get_carrier_employee()
            if employee_id:
                employee = Employee(employee_id)
                data['per_ent'] = unaccent(employee.rec_name)[:35]
            data['dir_ent'] = unaccent(waddress.street.replace('\n', ' - ')
                )[:60].rstrip()
            data['cp_ent'] = unaccent(waddress.postal_code)[:15]
            data['pob_ent'] = unaccent(waddress.city)[:40]
            data['pais_ent'] = unaccent(waddress.country and
                waddress.country.code or '')
            data['tel_ent'] = unspaces(api.phone or
                shipment.company.party.phone or '')[:20]
            if shipment.carrier_notes:
                data['obs1'] = unaccent(shipment.carrier_notes)[:38].rstrip()

            data['modelo'] = api.print_report

            resp = nacex_call(api, 'genEtiquetaDevolucion', data)

            values = resp.text.split('|', 1)

            if len(values) == 1 or resp.status_code != 200:
                message = gettext(
                    'carrier_send_shipments_nacex.msg_nacex_connection_error',
                    name=shipment.rec_name,
                    error=resp.text)
                errors.append(message)
                continue

            if values[0] == 'ERROR':
                message = gettext(
                    'carrier_send_shipments_nacex.msg_nacex_not_send_error',
                    name=shipment.rec_name,
                    error=resp.text)
                errors.append(message)
                continue

            reference = values[0]
            api_label = values[1]

            if reference:
                temp_name = cls.nacex_label_file(api, dbname, 'return', reference, api_label)
                if not temp_name:
                    continue
                labels.append(temp_name)

                cls.write([shipment], {
                    'carrier_tracking_ref': reference,
                    # 'carrier_service': service,
                    # 'carrier_delivery': True,
                    'carrier_send_date': ShipmentOutReturn.get_carrier_date(),
                    'carrier_send_employee': (
                        ShipmentOutReturn.get_carrier_employee() or None),
                    'carrier_printed': True,
                    'carrier_tracking_label': fields.Binary.cast(
                        open(temp_name, "rb").read()),
                    })
                logger.info('Send shipment %s' % (shipment.number))
                references.append(shipment.number)
            else:
                logger.error('Not send shipment %s.' % (shipment.number))

        return references, labels, errors
