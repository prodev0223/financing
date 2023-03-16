# -*- coding: utf-8 -*-
from odoo import models, fields, api, _, exceptions, tools
from datetime import datetime
from odoo.api import Environment
import threading
import odoo


class AmazonImportWizard(models.TransientModel):
    """
    Transient model/wizard that allows user to import Amazon XML files
    accepted types -- Amazon order/Amazon product. XML's are validated
    using XSD Schemas
    """
    _name = 'amazon.import.wizard'

    xml_data = fields.Binary(string='XML failas', required=True)
    xml_file_name = fields.Char(string='XML failo pavadinimas', size=128, required=False)
    xml_type = fields.Selection([('orders', 'Užsakymai'), ('products', 'Produktai')],
                                string='XML tipas', required=True, default='orders')

    @api.multi
    def button_xml_import(self):
        """
        Method called from the wizard button, that prepares Amazon XML
        import by creating threaded method that parses XML and creates objects
        :return: None
        """
        self.ensure_one()
        if not self.xml_data or not self.xml_type:
            raise exceptions.UserError(_('Nepaduotas XML failas arba nenurodytas XML tipas'))
        job_obj = self.env['amazon.import.wizard.job']
        if job_obj.search_count([('state', '=', 'in_progress'), ('xml_type', '=', self.xml_type)]):
            raise exceptions.ValidationError(
                _('Negalite atlikti veiksmo, XML failas yra importuojamas šiuo metu!'))
        vals = {
            'execution_start_date': datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT),
            'state': 'in_progress',
            'file_name': self.xml_file_name,
            'xml_type': self.xml_type
        }
        import_job = job_obj.create(vals)
        self.env.cr.commit()
        threaded_calculation = threading.Thread(
            target=self.thread_xml_import, args=(self.xml_data, self.xml_type, import_job.id, ))
        threaded_calculation.start()

    @api.multi
    def thread_xml_import(self, xml_data, xml_type, job_id):
        """
        Parse data from passed Amazon XML and create corresponding objects // THREADED
        :param xml_data: XML data in base64 format
        :param xml_type: Type of Amazon XML file (products/orders)
        :param job_id: amazon.import.wizard.job ID
        :return: None
        """
        with Environment.manage():
            new_cr = self.pool.cursor()
            env = api.Environment(new_cr, odoo.SUPERUSER_ID, {'lang': 'lt_LT'})
            job = env['amazon.import.wizard.job'].browse(job_id)
            try:
                if xml_type == 'orders':
                    order_list = env['amazon.xml.parsers'].parse_orders_xml(xml_data)
                    for order_values in order_list:
                        env['amazon.order'].create(order_values)
                else:
                    product_list = env['amazon.xml.parsers'].parse_product_xml(xml_data)
                    for product_values in product_list:
                        env['amazon.order'].create(product_values)
            except Exception as exc:
                new_cr.rollback()
                job.write({'state': 'failed',
                           'fail_message': str(exc.args[0]),
                           'execution_end_date': datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT)})
            else:
                job.write({'state': 'finished',
                           'execution_end_date': datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT)})
            new_cr.commit()
            new_cr.close()


AmazonImportWizard()
