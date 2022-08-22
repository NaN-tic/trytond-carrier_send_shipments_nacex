#This file is part of nacex. The COPYRIGHT file at the top level of
#this repository contains the full copyright notices and license terms.
import requests
import hashlib


def nacex_call(api, method, data):

    password = api.password
    if isinstance(password, str):
        password = password.encode('utf-8')
    url = '%s?method=%s&user=%s&pass=%s&data=%s' % (
        api.url,
        method, api.username,
        hashlib.md5(password).hexdigest(),
        nacex_data(data))
    return requests.get(url)


def nacex_data(data):
    return '|'.join(['%s=%s' % (key, value) for (key, value) in data.items()])

# def services():
#     services = {
        # '10': 'Entrega antes de las 10h',
        # '100': 'INT-COURIER',
        # '101': 'INT-BAG',
        # '14': 'Entrega antes de las 13h',
        # '200': 'EU-ESTANDAR',
        # '24': 'Entrega antes de las 19',
        # '300': 'EU-PACK',
        # '301': 'EU-BAG',
        # '72': 'Entrega antes de 72h',
        # '830': 'Entrega antes de las 8:30',
        # 'CM': 'Canarias Maritimo',
        # 'DEV': 'Devolucion',
        # 'E24': 'ECOMM 24 Entrega dia siguiente',
        # 'E72': 'ECOMM 72 Entrega en tres dias',
        # 'EEU': 'ECOMM Europe Express',
        # 'EWW': 'ECOMM Worldwide',
        # 'RCS': 'Retorno copia sellada',
        # 'RED': 'Recogeran en delegacion',
        # 'RET': 'Retorno',
        # 'SMD': 'Servicio Medio Dia',
        # 'V00': 'Valija Todo Dia',
        # 'V10': 'Valija 10h',
        # 'V14': 'Valija 14h',
#     }
#     return services
#
# def status_codes():
#     return {
        # '0': 'Documentado',
        # '1': 'En transito',
        # '2': 'En reparto',
        # '3': 'Incidencia',
        # '4': 'Entregado',
    # }
