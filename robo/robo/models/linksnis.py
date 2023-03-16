# -*- encoding: utf-8 -*-
import logging
from odoo import tools
import re
import traceback


_logger = logging.getLogger(__name__)


# todo: remember '-' position and use it in join


def kas_to_ko(words, *param):
    galunes = (("as", "o"), ("a", "os"), ("ė", "ės"), ("tysis", "čiojo"), ("nysis", "niojo"), ("ioji", "iosios"),
               ("tis", "čio"), ('tys', 'čio'), ("dis", "džio"), ("dys", "džio"), ("jis", "jo"), ("is", "io"),
               ("ys", "io"), ('iaus', 'iaus'), ("aus", "aus"), ("us", "aus"), ("ai", "ų"))
    return change_and_print(words, galunes, *param)


def kas_to_kam(words, *param):
    galunes = (("as", "ui"), ("a", "ai"), ("ė", "ei"), ("tis", "čiui"), ("tysis", "čiajam"), ("nysis", "niajam"),
               ("ioji", "iajai"), ("dys", "džiui"), ("tys", "čiui"), ("dis", "džiui"), ("jis", "jui"), ("is", "iui"),
               ("ys", "iui"), ('iaus', 'iaus'), ("us", "ui"))
    return change_and_print(words, galunes, *param)


def kas_to_ka(words, *param):
    galunes = (('aus', 'ų'), ('as', 'ą'), ('a', 'ą'), ('ė', 'ę'), ('is', 'į'), ('iaus', 'iaus'), ('us', 'ų'),
               ('ys', 'į'), ("ysis", "įjį"), ("ioji", "iąją"))
    return change_and_print(words, galunes, *param)


def kas_to_kuo(words, *param):
    galunes = (("as", "u"), ("ė", "e"), ("tis", "čiu"), ("dis", "džiu"), ("jis", "ju"), ("tysis", "čioju"),
               ("nysis", "niuoju"), ("ioji", "ąja"), ('is', 'iu'), ('iaus', 'iaus'), ('us', 'umi'), ('tys', 'čiu'),
               ("dys", "džiu"), ("ius", "iumi"), ("ys", "iu"))
    return change_and_print(words, galunes, *param)


def kas_to_kur(words, *param):
    galunes = (('as', 'e'), ('a', 'oje'), ('ė', 'ėje'), ('is', 'yje'), ('iaus', 'iaus'), ('us', 'uje'), ('ys', 'yje'))
    return change_and_print(words, galunes, *param)


def kas_to_sauksm(words, *param):
    galunes = (('as', 'ai'), ('ė', 'e'), ('is', 'i'), ('iaus', 'iaus'), ('us', 'au'), ('ys', 'y'))
    return change_and_print(words, galunes, *param)


# tools

def change_and_print(words, galunes, *param):
    if isinstance(words, basestring):
        return print_form(' '.join([pakeisti_galune(w, galunes) for w in re.split("[ -]", words)]), *param)
    return print_form(words, *param)


def print_form(words, *param):
    if not param or not param[0]:
        kodas = ''
    else:
        kodas = param[0]
    try:
        if kodas == 'AA':
            return words.upper()
        elif kodas == 'aa':
            return words.lower()
        if kodas == 'Aa':
            result = ''
            for word in words.lower().split(' '):
                if word:
                    result += word[0].upper() + word[1:] + ' '
                else:
                    result += ' '
            return result[:-1]
        return words
    except AttributeError as exc:
        _logger.info('Failed to use function upper()/lower() on variable expected to be of string type: {}.\n Error: {}'
                     '\nTraceback: {}'.format(tools.ustr(words), tools.ustr(exc), traceback.format_exc))
        return ''


def pakeisti_galune(word, galunes):
    try:
        word = word.decode('utf-8')
    except:
        pass
    for g in galunes:
        if word.endswith(g[0]):
            return word[:len(word) - len(g[0].decode('utf-8'))] + g[1]
        elif word.lower().endswith(g[0]):
            return word[:len(word) - len(g[0].decode('utf-8'))] + g[1].upper()
    return word
