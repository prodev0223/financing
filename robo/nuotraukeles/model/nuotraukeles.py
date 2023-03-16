# -*- coding: utf-8 -*-
from odoo import models, fields, _, api, tools, exceptions
from PIL import Image
from PIL import ImageFont
from PIL import ImageDraw
from PIL import ImageOps
from PIL import ImageFilter
import unicodedata
import random
try:
    import cStringIO as StringIO
except ImportError:
    import StringIO


def remove_accents(input_str):
    nkfd_form = unicodedata.normalize('NFKD', input_str)
    only_ascii = nkfd_form.encode('ASCII', 'ignore')
    return only_ascii


class DarbuotojoSpalvos(models.Model):

    _inherit = 'hr.employee'

    spalva = fields.Char(string='Color', default='#040E62')
    image = fields.Binary(inverse='_set_image')
    user_id = fields.Many2one('res.users', inverse='_set_image')
    address_home_id = fields.Many2one('res.partner')

    # Removing the inverse call since this module is not installed
    # anywhere (nor it will be) and it can cause problems
    @api.one
    def _set_image(self):
        if self.image and not self._context.get('skip_inverse', False):
            if self.user_id:
                self.user_id.image = self.image
                if self.user_id.partner_id:
                    self.user_id.partner_id.image = self.image
            if self.address_home_id:
                self.address_home_id.image = self.image

    @api.onchange('active')
    def _default_color(self):
        '''
        :return: string in color hex code, ex. #040E62
        '''
        r = int(random.random()*200)
        g = int(random.random()*200)
        b = int(random.random()*200)
        hr = hex(r)[2:]
        hg = hex(g)[2:]
        hb = hex(b)[2:]
        if len(hr) == 1:
            hr = '0' + hr
        if len(hg) == 1:
            hg = '0' + hg
        if len(hb) == 1:
            hb = '0' + hb
        self.spalva = '#' + hr + hg + hb

    @api.onchange('name', 'spalva')
    def onchange_name_color(self):
        if self.name:
            vardas = self.name
            vardas = vardas.replace('-', ' ')
            vardas = vardas.strip()
            vardas = vardas.split(' ')
            krastine = 180
            if len(vardas) >= 1:
                if vardas[0]:
                    v1 = vardas[0][0]
                else:
                    v1 = ''
                if v1 and isinstance(v1, (str, unicode)):
                    v1 = v1.upper()
                if len(vardas) == 2 and vardas[1]:
                    v2 = vardas[1][0]
                elif len(vardas) == 3 and vardas[2]:
                    v2 = vardas[2][0]
                else:
                    v2 = ''
                if v2 and isinstance(v2, (str, unicode)):
                    v2 = v2.upper()
                inicialai = v1 + v2
                spalva = self.spalva
                if spalva:
                    im = Image.new('RGB', (krastine, krastine), spalva)
                else:
                    im = Image.new('RGB', (krastine, krastine), (5, 15, 100))
                draw = ImageDraw.Draw(im)
                fontas = False
                kompanijos_font = self.sudo().company_id.font
                if kompanijos_font and kompanijos_font.path and '.ttf' in kompanijos_font.path:
                    fontas = kompanijos_font.path
                if not fontas:
                    res_fonts = self.env['res.font'].search([], limit=1)
                    if res_fonts and '.ttf' in res_fonts.path:
                        fontas = res_fonts.path

                if fontas:
                    font = ImageFont.truetype(fontas, 120)
                else:
                    font = ImageFont.load_default()

                w, h = font.getsize(inicialai)
                draw.text(((krastine-w)/2, (krastine-h)/2-10), inicialai, (255, 255, 255), font=font)
                size = (krastine, krastine)
                mask = Image.new('L', size, 0)
                draw_mask = ImageDraw.Draw(mask)
                draw_mask.ellipse((0, 0) + size, fill=255)
                mask = mask.filter(ImageFilter.SMOOTH_MORE)
                output = ImageOps.fit(im, mask.size, centering=(0.5, 0.5))
                output.putalpha(mask)
                output = output.filter(ImageFilter.SMOOTH_MORE)
                jpeg_image_buffer = StringIO.StringIO()
                output.save(jpeg_image_buffer, format='PNG')
                val = jpeg_image_buffer.getvalue().encode('base64')
                self.image = val

                # dalis1 = remove_accents(vardas[0]).lower()
                # if len(vardas) == 2:
                #     dalis2 = remove_accents(vardas[1]).lower()
                # elif len(vardas) == 3:
                #     dalis2 = remove_accents(vardas[2]).lower()
                # else:
                #     dalis2 = ''
                # domenas = ''
                # if self.company_id.email:
                #     domenai = self.company_id.email.split('@')
                #     if len(domenai) == 2:
                #         domenas = '@' + domenai[1]
                # start = dalis1
                # if dalis2:
                #     start += '.' + dalis2
                # self.work_email = start + domenas

DarbuotojoSpalvos()
