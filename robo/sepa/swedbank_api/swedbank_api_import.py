# -*- encoding: utf-8 -*-
import subprocess32 as subprocess
from odoo import models, _, api
from datetime import datetime
import swedbank_tools as st
import os


class SwedBankAPIImport(models.TransientModel):
    _name = 'swed.bank.api.import'
    _description = 'Transient model that is used for automatic bank statement exports from SwedBank using API solutions'

    @api.multi
    def push_bank_statements(self, prep_data):
        """
        Method that is used to pass XML files from the system to SwedBank using provided token.
        XML files that match PAIN schema are supported
        """

        sd = st.get_swed_data(self.env)
        sending_path = sd.get('directory_path') + '/sending'
        if not os.path.isdir(sending_path):
            os.mkdir(sending_path)
        file_name = self.env.cr.dbname + '__pain_03_' + datetime.utcnow().strftime('%m-%d-%Y_%H%M%S') + \
                    '_' + self.env.user.sudo().company_id.company_registry + '.xml'
        abs_path = sending_path + '/' + file_name
        with open(abs_path, 'w+') as fh:
            fh.write(prep_data['xml_stream'])
        agr_id = self.env.user.sudo().company_id.swed_bank_agreement_id
        os.chdir(sd.get('directory_path'))
        if not agr_id:
            self.env.cr.rollback()
            return {
                'type': 'ir.actions.act_window',
                'res_model': 'swed.bank.api.import',
                'view_mode': 'form',
                'view_type': 'form',
                'views': [(False, 'form')],
                'target': 'new',
                'view_id': self.env.ref('sepa.form_swed_bank_api_import_info_wizard').id,
            }
        command = './send.sh url=%s agreementId=%s file=sending/%s erpCert=certs/%s transportCert=certs/%s ' \
                  'dir=received' % (sd.get('main_url'), str(agr_id), file_name, sd.get('cert_path'), sd.get('cert_path'))
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=None, executable='/bin/bash', shell=True)
        st.handle_timeout(process)


SwedBankAPIImport()
