import base64
import unittest
from functools import partial
from tempfile import NamedTemporaryFile, TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from proteus import Model, Wizard
from trytond.modules.company.tests.tools import create_company, get_company
from trytond.tests.test_tryton import drop_db
from trytond.tests.tools import activate_modules


class TestPrintLabels(unittest.TestCase):

    def setUp(self):
        drop_db()
        super().setUp()

    def tearDown(self):
        drop_db()
        super().tearDown()

    def test(self):
        activate_modules('carrier_send_shipments_nacex')
        create_company()
        company = get_company()
        Party = Model.get('party.party')
        Template = Model.get('product.template')
        Uom = Model.get('product.uom')
        Carrier = Model.get('carrier')
        Api = Model.get('carrier.api')
        Location = Model.get('stock.location')
        Shipment = Model.get('stock.shipment.out')
        Attachment = Model.get('ir.attachment')

        customer = Party(name='Customer')
        customer.save()
        carrier_party = Party(name='Nacex')
        carrier_party.save()
        unit, = Uom.find([('name', '=', 'Unit')])
        template = Template(name='Shipping', type='service', default_uom=unit)
        template.save()
        product, = template.products
        carrier = Carrier(party=carrier_party, carrier_product=product)
        carrier.save()
        api = Api(name='Nacex', company=company, method='nacex',
            url='https://example.invalid', username='test', password='test',
            vat='TEST', nacex_delegacion='0801', nacex_abonado='12345',
            print_report='IMAGEN_B')
        api.carriers.append(carrier)
        api.save()
        warehouse, = Location.find([('code', '=', 'WH')])

        # A PNG returned by the carrier, with standard or Nacex padding,
        # line wrapping, and omitted padding.
        encoded = ('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABAQAAAAA3bvkk'
            'AAAACklEQVR4nGNgAAAAAgABSK+kcQAAAABJRU5ErkJggg==')
        content = base64.b64decode(encoded)
        nacex = encoded.replace('=', '*')
        responses = [encoded, nacex, '\r\n'.join(
            nacex[i:i + 4] for i in range(0, len(nacex), 4)),
            encoded.rstrip('=') + '\n',
            encoded.replace('/', '_').replace('+', '-'),
            'abcde', 'ab!c', '', 'not an image: ò']
        module = 'trytond.modules.carrier_send_shipments_nacex.shipment'
        with TemporaryDirectory() as directory, patch(
                module + '.tempfile.NamedTemporaryFile',
                partial(NamedTemporaryFile, dir=directory)):
            for index, response in enumerate(responses):
                with self.subTest(response=index):
                    shipment = Shipment(customer=customer, company=company,
                        warehouse=warehouse, carrier=carrier)
                    # The tracking reference makes the carrier readonly.
                    shipment.save()
                    shipment.carrier_tracking_ref = '0801/123456'
                    shipment.save()
                    wizard = Wizard('carrier.print.shipment', [shipment])
                    with patch(module + '.nacex_call', return_value=
                            SimpleNamespace(status_code=200, text=response)):
                        wizard.execute('print_')
                    shipment.reload()
                    attachments = Attachment.find([
                        ('resource', '=', str(shipment))])
                    if index < 5:
                        self.assertEqual(wizard.form.labels, content)
                        self.assertEqual(shipment.carrier_tracking_label,
                            content)
                        self.assertTrue(shipment.carrier_printed)
                        attachment, = attachments
                        self.assertEqual(attachment.data, content)
                    else:
                        self.assertFalse(wizard.form.labels)
                        self.assertFalse(shipment.carrier_tracking_label)
                        self.assertFalse(shipment.carrier_printed)
                        self.assertFalse(attachments)
                    self.assertEqual(shipment.carrier_tracking_ref,
                        '0801/123456')
                    wizard.execute('end')
