import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from proteus import Model

from trytond.exceptions import UserError
from trytond.modules.company.tests.tools import create_company, get_company
from trytond.tests.test_tryton import drop_db
from trytond.tests.tools import activate_modules


class TestNacexConnection(unittest.TestCase):

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
        self.assertFalse(api.md5)

        digest = '5f4dcc3b5aa765d61d8327deb882cf99'
        with patch('trytond.modules.carrier_send_shipments_nacex.utils.'
                'requests.get') as request:
            request.return_value.text = 'Agency found'
            with self.assertRaisesRegex(UserError, 'Agency found'):
                api.click('test_connection')
            request.assert_called_once()
            query = parse_qs(urlsplit(request.call_args.args[0]).query)
            self.assertEqual(query['pass'], [digest])
            self.assertEqual(query['method'], ['getAgencia'])

            api.md5 = True
            api.password = digest
            api.save()
            request.reset_mock()
            with self.assertRaisesRegex(UserError, 'Agency found'):
                api.click('test_connection')
            request.assert_called_once()
            query = parse_qs(urlsplit(request.call_args.args[0]).query)
            self.assertEqual(query['pass'], [digest])
