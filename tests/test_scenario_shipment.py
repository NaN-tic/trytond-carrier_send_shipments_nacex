import unittest
from unittest.mock import patch
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

from proteus import Model

from trytond.pool import Pool
from trytond.transaction import Transaction
from trytond.modules.company.tests.tools import create_company, get_company
from trytond.tests.test_tryton import drop_db
from trytond.tests.tools import activate_modules


class TestNacexShipment(unittest.TestCase):

    def setUp(self):
        drop_db()
        super().setUp()

    def tearDown(self):
        drop_db()
        super().tearDown()

    def test(self):
        config = activate_modules('carrier_send_shipments_nacex')
        create_company(config=config)
        Api = Model.get('carrier.api')
        Carrier = Model.get('carrier')
        Party = Model.get('party.party')
        Template = Model.get('product.template')
        Uom = Model.get('product.uom')

        unit, = Uom.find([('name', '=', 'Unit')])
        template = Template(name='Delivery', type='service', default_uom=unit)
        template.save()
        party = Party(name='Nacex')
        party.save()
        carrier = Carrier(party=party, carrier_product=template.products[0])
        carrier.save()
        api = Api(name='Nacex', company=get_company(config=config),
            method='nacex', url='https://nacex.example.test',
            username='test', password='password', vat='TEST',
            nacex_delegacion='0001', nacex_abonado='000001')
        api.carriers.append(carrier)
        api.save()
        api.services.new(name='Delivery', code='01')
        api.print_report = 'ZEBRA_B'
        api.save()
        api.default_service = api.services[0]
        api.save()

        Country = Model.get('country.country')
        Location = Model.get('stock.location')
        Shipment = Model.get('stock.shipment.out')
        country = Country(name='Spain', code='ES')
        country.save()
        customer = Party(name='Customer')
        address, = customer.addresses
        address.street = 'Main street 1'
        address.postal_code = '08001'
        address.city = 'Barcelona'
        address.country = country
        customer.save()
        warehouse, = Location.find([('type', '=', 'warehouse')])
        shipment = Shipment(number='OUT-TEST', customer=customer,
            delivery_address=customer.addresses[0], warehouse=warehouse,
            carrier=carrier)
        shipment.save()

        label = '^XA^FO50,50^FDNacex test label^FS^XZ'
        with patch('trytond.modules.carrier_send_shipments_nacex.utils.'
                'requests.get', side_effect=[
                    SimpleNamespace(status_code=200, text='123|0001/123|'),
                    SimpleNamespace(status_code=200, text=label),
                    ]) as request:
            with Transaction().start(config.database_name, config.user,
                    context=config.context):
                ShipmentModel = Pool().get('stock.shipment.out')
                record = ShipmentModel(shipment.id)
                references, labels, errors = (
                    ShipmentModel.send_shipment_api(record))
                try:
                    self.assertEqual(errors, [])
                    self.assertEqual(references, [record.number])
                    self.assertEqual(len(labels), 1)
                    self.assertEqual(Path(labels[0]).read_bytes(),
                        label.encode())
                    self.assertEqual(record.carrier_tracking_ref, '0001/123')
                    self.assertTrue(record.carrier_delivery)
                    self.assertTrue(record.carrier_printed)
                    self.assertEqual(record.carrier_tracking_label,
                        label.encode())
                finally:
                    for filename in labels:
                        Path(filename).unlink()
            self.assertEqual(request.call_count, 2)
            methods = [parse_qs(urlsplit(call.args[0]).query)['method'][0]
                for call in request.call_args_list]
            self.assertEqual(methods, ['putExpedicion', 'getEtiqueta'])
