# This file is part of the carrier_send_shipments module for Tryton.
# The COPYRIGHT file at the top level of this repository contains
# the full copyright notices and license terms.
import logging
import tempfile
import base64
from trytond.pool import Pool, PoolMeta
from trytond.model import fields
from trytond.transaction import Transaction
from trytond.i18n import gettext
from trytond.exceptions import UserError
from trytond.modules.carrier_send_shipments.tools import unaccent, unspaces
from .utils import nacex_call

__all__ = ['ShipmentOut']

logger = logging.getLogger(__name__)


class ShipmentOut(metaclass=PoolMeta):
    __name__ = 'stock.shipment.out'
    nacex_envase = fields.Selection('get_nacex_envase', 'Nacex Envase')

    @staticmethod
    def get_nacex_envase():
        Api = Pool().get('carrier.api')
        selection = Api.fields_get(
            ['nacex_envase'])['nacex_envase']['selection']
        return [(None, '')] + selection

    @staticmethod
    def default_nacex_envase():
        return None

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
            service = shipment.carrier_service or shipment.carrier.service or default_service
            if not service:
                message = gettext('carrier_send_shipments_nacex.msg_nacex_add_services')
                errors.append(message)
                continue

            if api.reference_origin and hasattr(shipment, 'origin'):
                code = shipment.origin and shipment.origin.rec_name or shipment.number
            else:
                code = shipment.number

            packages = shipment.number_packages
            if not packages or packages == 0:
                packages = 1

            weight = 1
            if api.weight and hasattr(shipment, 'weight_func'):
                weight = shipment.weight_func
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
                    raise UserError(
                        gettext('carrier_send_shipments_nacex.msg_missing_warehouse_address'))
                waddress = waddresses[0]

            # TODO upgrade 6.0 rename zip to postal_code
            data = {}
            data['del_cli'] = api.nacex_delegacion[:4]
            data['num_cli'] = api.nacex_abonado[:5]
            data['fec'] = Date.today().strftime("%d/%m/%Y")
            data['tip_ser'] = service.code
            data['tip_cob'] = 'T' # TODO
            data['ref_cli'] = code[:20]
            data['tip_env'] = shipment.nacex_envase or api.nacex_envase or '2'
            data['bul'] = packages
            data['kil'] = str(weight)
            data['nom_rec'] = unaccent(api.company.party.name)[:35]
            data['dir_rec'] = unaccent(waddress.street)[:60].rstrip()
            data['cp_rec'] = unaccent(waddress.zip)[:8]
            data['pob_rec'] = unaccent(waddress.city)[:30]
            data['pais_rec'] = unaccent(waddress.country and waddress.country.code or '')
            data['tel_rec'] = unspaces(api.phone or shipment.company.party.phone or '')[:35]
            data['nom_ent'] = unaccent(shipment.customer.name)[:35]
            data['per_ent'] = unaccent((shipment.delivery_address.party_name
                    or shipment.customer.name))[:35]
            data['dir_ent'] = unaccent(shipment.delivery_address.street)[:60].rstrip()
            data['cp_ent'] = unaccent(shipment.delivery_address.zip)[:60]
            data['pob_ent'] = unaccent(shipment.delivery_address.city)[:30]
            data['pais_ent'] = unaccent(shipment.delivery_address.country
                and shipment.delivery_address.country.code or '')
            data['tel_ent'] = unspaces(shipment.customer.mobile or shipment.customer.phone or '')[:15]
            if shipment.carrier_notes:
                data['obs1'] = unaccent(shipment.carrier_notes)[:38].rstrip()

            resp = nacex_call(api, 'putExpedicion', data)
            values = resp.text.split('|')

            if len(values) == 1 or resp.status_code != 200:
                message = gettext('carrier_send_shipments_nacex.msg_nacex_connection_error',
                    name=shipment.rec_name,
                    error=resp.text)
                errors.append(message)
                continue

            if values[0] == 'ERROR':
                message = gettext('carrier_send_shipments_nacex.msg_nacex_not_send_error',
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
                    'carrier_send_employee': ShipmentOut.get_carrier_employee() or None,
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
            data['modelo'] = api.nacex_print

            resp = nacex_call(api, 'getEtiqueta', data)
            values = resp.text.split('|')

            if resp.status_code != 200 or values[0] == 'ERROR':
                continue

            if api.nacex_print == 'IMAGEN_B':
                try:
                    content = base64.urlsafe_b64decode(
                        resp.text + '=' * (4 - len(resp.text) % 4))
                except TypeError:
                    continue
                suffix = '.png'
            else:
                try:
                    content = resp.text.encode()
                except AttributeError:
                    continue
                suffix = None

            with tempfile.NamedTemporaryFile(
                    prefix='%s-nacex-%s-%s-' % (dbname, agencia, numero),
                    suffix=suffix, delete=False) as temp:
                temp.write(content)
            logger.info(
                'Generated tmp label %s' % (temp.name))
            temp.close()
            labels.append(temp.name)

            to_write.extend(([shipment], {
                    'carrier_tracking_label': fields.Binary.cast(
                        open(temp.name, "rb").read()),
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
