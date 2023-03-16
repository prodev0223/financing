# -*- coding: utf-8 -*-
from lxml import etree, objectify
from lxml.etree import XMLSyntaxError
from odoo import tools, exceptions, _
from datetime import datetime


FORM_CODE_MAPPING = {
    'FR0438': '9C7789C4-1B12-4449-90CE-C6367FC80E0C',
    'FR0521': 'E503952D-8BFE-4796-8979-70096A287EB3',
    'PLN204': '8C027243-9B55-4DF5-91F4-EF6AB1684F0E',
}


def set_tag(node, tag, value):
    """
    Sets tag on passed etree node
    :param node: Node on which the tag should be set
    :param tag: Node tag name
    :param value: Node tag value
    :return: None
    """
    if isinstance(value, (float, int)) and not isinstance(value, bool):
        value = str(value)
    node.attrib[tag] = value


def set_node_and_tag(p_node, c_tag, c_text, c_node='Field', c_tag_key='Name'):
    """
    Creates new etree node in passed parent node and sets the specified tag
    :param p_node: Parent node, etree object (in which the new node should be created)
    :param c_tag: to-be-created Child node tag value
    :param c_text: to-be-created Child node text
    :param c_node: to-be-created Child node name
    :param c_tag_key: to-be-created Child node tag key
    :return: None
    """
    el = etree.Element(c_node)
    if isinstance(c_text, (float, int)) and not isinstance(c_text, bool):
        c_text = str(c_text)
    if c_text:
        el.text = c_text
    else:
        el.text = ''
    if isinstance(c_tag, (float, int)) and not isinstance(c_tag, bool):
        c_tag = str(c_tag)
    el.attrib[c_tag_key] = c_tag
    p_node.append(el)


def prepare_chunks(data_set, size):
    """
    GENERATOR -- Splits data set in set of passed size
    :param data_set: any list
    :param size: chunk size
    :return: Split list
    """
    for it in range(0, len(data_set), size):
        yield list(data_set[it:it + size])


def get_report_header(form_type):
    """
    Method that returns static XML header
    :return: str -- Header
    """
    header = '''<?xml version="1.0" encoding="UTF-8"?>
    <FFData Version="1" CreatedByLogin="ROBO" CreatedOn="%s">
    </FFData>
    ''' % datetime.now().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
    header_obj = objectify.fromstring(header)
    form_code = FORM_CODE_MAPPING.get(form_type)

    form = '''<Form FormDefId="{%s}">
    </Form>''' % form_code
    form_obj = objectify.fromstring(form)
    header_obj.append(form_obj)

    return form_obj, header_obj


def xml_validator(some_xml_string, xsd_file='/path/to/my_schema_file.xsd'):
    try:
        schema = etree.XMLSchema(file=xsd_file)
        parser = objectify.makeparser(schema=schema)
        objectify.fromstring(some_xml_string, parser)
        return True
    except XMLSyntaxError as exc:
        raise exceptions.ValidationError(_('Failed to generate file:\n%s') % exc.message)


def round_to_int(num_float):
    return int(round(tools.float_round(num_float, precision_digits=2)))


def convert_to_str(num_float):
    return ('%.2f' % num_float).replace('.', ',')


def float_to_str(num_float, digits=2):
    return '%.{0}f'.format(digits) % num_float


def convert_to_int_str(num_float):
    num_int = round_to_int(num_float)
    return '%d' % num_int


# Variables used for FR0521
GASOLINE_PRODUCT = 'Kuras-benzinas'
DIESEL_PRODUCT = 'Kuras-dyzelinas'
GAS_PRODUCT = 'Kuras-dujos'

PAGE_POPULATION_THRESHOLD_0521 = 8
STATIC_FIELD_COUNT_0521 = '96'

PRODUCT_NAMES_0521 = [GASOLINE_PRODUCT, DIESEL_PRODUCT, GAS_PRODUCT]

PRODUCT_RATES_0521 = {
    GASOLINE_PRODUCT: 0.75,
    DIESEL_PRODUCT: 0.84,
    GAS_PRODUCT: 0.54
}

PRODUCT_CODES_0521 = {
    GASOLINE_PRODUCT: '1',
    DIESEL_PRODUCT: '2',
    GAS_PRODUCT: '3'
}
# // Variables used for FR0521

# Variables used for SAF-T
SAFT_DATA_TYPE = [
    ('F', 'Pilna rinkmena'),
    # We do not use the remaining types for now
    # ('GL', 'Didžiosios knygos duomenys'),
    # ('PI', 'Pirkimų duomenys'),
    # ('PA', 'Mokėjimų duomenys'),
    # ('SI', 'Pardavimų duomenys'),
    # ('MG', 'Prekių judėjimo duomenys'),
    # ('AS', 'Ūkinių operacijų ar ūkinių įvykių dėl turto duomenys')
]

SAFT_ACCOUNT_TYPE_MAPPER = {
    'Ilgalaikis turtas': 'IT',
    'Trumpalaikis turtas': 'TT',
    'Kapitalas': 'NK',
    'Ilgalaikiai įsipareigojimai': 'I',
    'Trumpalaikiai įsipareigojimai': 'I',
    'Pajamos': 'P',
    'Sąnaudos': 'S',
    'Kita': 'KT'
}

SAFT_INVOICE_TYPE_MAPPER = {
    'in_invoice': 'S',
    'in_refund': 'K',
    'out_invoice': 'SF',
    'out_refund': 'KS',
}

SAFT_MOVEMENT_TYPE = {
    'PARD': 'Pardavimas',
    'PIR': 'Pirkimas',
    'PP': 'Pagaminta produkcija',
    'PG': 'Pardavimų grąžinimas',
    'PRG': 'Pirkimų grąžinimas',
    'VP': 'Vidinis perkėlimas',
    'N': 'Nurašymas',
    'KT': 'Kita',
}

SAFT_PRODUCTION_MOVEMENTS = ['PP']
# // Variables used for SAF-T

SKYRIAI = [
    ('32', 'Akmenės skyriui'),
    ('11', 'Alytaus skyriui'),
    ('34', 'Anykščių skyriui'),
    ('12', 'Birštono skyriui'),
    ('36', 'Biržų skyriui'),
    ('15', 'Druskininkų skyriui'),
    ('42', 'Elektrėnų skyriui'),
    ('45', 'Ignalinos skyriui'),
    ('46', 'Jonavos skyriui'),
    ('47', 'Joniškio skyriui'),
    ('94', 'Jurbarko skyriui'),
    ('49', 'Kaišiadorių skyriui'),
    ('48', 'Kalvarijos skyriui'),
    ('nera', 'Karinių ir joms prilygintų struktūrų skyriui'),
    ('19', 'Kauno skyriui'),
    ('58', 'Kazlų Rūdos skyriui'),
    ('53', 'Kėdainių skyriui'),
    ('54', 'Kelmės skyriui'),
    ('21', 'Klaipėdos skyriui'),
    ('56', 'Kretingos skyriui'),
    ('57', 'Kupiškio skyriui'),
    ('59', 'Lazdijų skyriui'),
    ('18', 'Marijampolės skyriui'),
    ('61', 'Mažeikių skyriui'),
    ('62', 'Molėtų skyriui'),
    ('23', 'Neringos skyriui'),
    ('63', 'Pagėgių skyriui'),
    ('65', 'Pakruojo skyriui'),
    ('25', 'Palangos skyriui'),
    ('27', 'Panevėžio skyriui'),
    ('67', 'Pasvalio skyriui'),
    ('68', 'Plungės skyriui'),
    ('69', 'Prienų skyriui'),
    ('71', 'Radviliškio skyriui'),
    ('72', 'Raseinių skyriui'),
    ('74', 'Rietavo skyriui'),
    ('73', 'Rokiškio skyriui'),
    ('75', 'Skuodo skyriui'),
    ('84', 'Šakių skyriui'),
    ('85', 'Šalčininkų skyriui'),
    ('29', 'Šiaulių skyriui'),
    ('87', 'Šilalės skyriui'),
    ('88', 'Šilutės skyriui'),
    ('89', 'Širvintų skyriui'),
    ('86', 'Švenčionių skyriui'),
    ('77', 'Tauragės skyriui'),
    ('78', 'Telšių skyriui'),
    ('79', 'Trakų skyriui'),
    ('81', 'Ukmergės skyriui'),
    ('82', 'Utenos skyriui'),
    ('38', 'Varėnos skyriui'),
    ('39', 'Vilkaviškio skyriui'),
    ('13', 'Vilniaus skyriui'),
    ('30', 'Visagino skyriui'),
    ('43', 'Zarasų skyriui'),
    ('41', 'Vilniaus r.'),
]

SKYRIAI_VALUES = {
    '32': 'Akmenės skyriui',
    '11': 'Alytaus skyriui',
    '34': 'Anykščių skyriui',
    '12': 'Birštono skyriui',
    '36': 'Biržų skyriui',
    '15': 'Druskininkų skyriui',
    '42': 'Elektrėnų skyriui',
    '45': 'Ignalinos skyriui',
    '46': 'Jonavos skyriui',
    '47': 'Joniškio skyriui',
    '94': 'Jurbarko skyriui',
    '49': 'Kaišiadorių skyriui',
    '48': 'Kalvarijos skyriui',
    'nera': 'Karinių ir joms prilygintų struktūrų skyriui',
    '19': 'Kauno skyriui',
    '58': 'Kazlų Rūdos skyriui',
    '53': 'Kėdainių skyriui',
    '54': 'Kelmės skyriui',
    '21': 'Klaipėdos skyriui',
    '56': 'Kretingos skyriui',
    '57': 'Kupiškio skyriui',
    '59': 'Lazdijų skyriui',
    '18': 'Marijampolės skyriui',
    '61': 'Mažeikių skyriui',
    '62': 'Molėtų skyriui',
    '23': 'Neringos skyriui',
    '63': 'Pagėgių skyriui',
    '65': 'Pakruojo skyriui',
    '25': 'Palangos skyriui',
    '27': 'Panevėžio skyriui',
    '67': 'Pasvalio skyriui',
    '68': 'Plungės skyriui',
    '69': 'Prienų skyriui',
    '71': 'Radviliškio skyriui',
    '72': 'Raseinių skyriui',
    '74': 'Rietavo skyriui',
    '73': 'Rokiškio skyriui',
    '75': 'Skuodo skyriui',
    '84': 'Šakių skyriui',
    '85': 'Šalčininkų skyriui',
    '29': 'Šiaulių skyriui',
    '87': 'Šilalės skyriui',
    '88': 'Šilutės skyriui',
    '89': 'Širvintų skyriui',
    '86': 'Švenčionių skyriui',
    '77': 'Tauragės skyriui',
    '78': 'Telšių skyriui',
    '79': 'Trakų skyriui',
    '81': 'Ukmergės skyriui',
    '38': 'Varėnos skyriui',
    '39': 'Vilkaviškio skyriui',
    '13': 'Vilniaus skyriui',
    '41': 'Vilniaus r.',
    '30': 'Visagino skyriui',
    '43': 'Zarasų skyriui',
}
