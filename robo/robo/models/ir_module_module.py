# -*- coding: utf-8 -*-
import logging

import odoo
from odoo import SUPERUSER_ID, api, fields, models, modules, tools
from odoo.modules import load_information_from_description_file
from odoo.addons.queue_job.job import job

_logger = logging.getLogger(__name__)


class IrModuleModule(models.Model):
    _inherit = 'ir.module.module'

    @api.model
    def response(self, text, code):
        """Returns a simulated API response structure"""
        if code != 200:
            self.env.cr.rollback()
        return {
            'error': text if code != 200 else str(),
            'message': text if code == 200 else str(),
            'status_code': code,
        }

    @api.model
    @job
    def reload_data_file(self, module, filename=None, filenames=None):
        """
        Reload a given file from the module manifest
        :param module: module name (str)
        :param filename: filename with relative path as in the 'data' section of manifest file
        :param filenames: list of filenames with relative path as in the 'data' section of manifest file. Files will be
                          loaded in the same order as they are in manifest file
        :return: {'status_code': HTTP code, 'error': error if code is not 200, 'message': str}
        """

        try:
            if filename is None and filenames is None:
                return self.response("You need to provide either 'filename' or 'filenames' argument", 401)
            if filenames is None:
                filenames = []
            if filename:
                filenames.append(filename)
            filenames = set(filenames)
            data = load_information_from_description_file(module)['data']
            for f in filenames:
                if f not in data:
                    return self.response("File '%s' is not in the list of files to be loaded" % f, 401)

            if len(filenames) > 1:
                order = {f: i for i, f in enumerate(data)}
                filenames = sorted(filenames, key=lambda x: order[x])

            report = tools.assertion_report.assertion_report()

            for f in filenames:
                _logger.info("module %s: reloading %s", module, f)
                tools.convert_file(self._cr, module, f, {}, mode='update', noupdate=False, kind='data', report=report)

            return self.response('%s' % report, 200)
        except Exception as exc:
            import traceback
            message = traceback.format_exc()
            _logger.info('File reloading error: %s\n%s' % (str(exc.args), message))
            return self.response('Unexpected error', 500)

    @api.model
    def reload_module_ignoring_dep(self, module):
        """
        Reloads the module ignoring its dependencies
        :param module: module name
        :return: {'status_code': HTTP code, 'error': error if code is not 200, 'message': str}
        """
        ir_module = self.search([('name', '=', module)])
        if not ir_module:
            self.response('Passed module [%s] was not found in the system' % module, 401)
        try:
            ir_module.write({'state': 'to upgrade'})
            self._cr.commit()
            api.Environment.reset()
            modules.registry.Registry.new(self._cr.dbname, update_module=True)
            return self.response(str(), 200)
        except Exception as exc:
            import traceback
            message = traceback.format_exc()
            _logger.info('Module [%s] reloading error: %s\n%s' % (module, str(exc.args), message))
            return self.response('Unexpected error', 500)

    @api.model
    def reload_module_tables(self, module, model_names=None):
        """
        Reload the tables of the models for the given module name.
        If model names are not passed, all models/tables are reloaded
        :param module: System module name (robo, sepa etc.)
        :param model_names: list of model names for this module ['account.invoice', 'res.partner'] etc.
        :return: {'status_code': HTTP code, 'error': error if code is not 200, 'message': str}
        """

        models_to_exclude = ['script', 'res.users', 'res.users.chart.settings', 'res.users.chart.settings.line']
        model_names = [] if model_names is None else model_names
        db_name = self._cr.dbname

        registry_cls = modules.registry.Registry
        with registry_cls._lock:
            with odoo.api.Environment.manage():
                registry = object.__new__(registry_cls)
                registry.init(db_name)
                registry_cls.delete(db_name)
                registry_cls.registries[db_name] = registry
                try:
                    registry.setup_signaling()
                    # This should be a method on Registry
                    try:
                        cr = registry._db.cursor()
                        registry.setup_models(cr, partial=True)
                        env = api.Environment(cr, SUPERUSER_ID, {})
                        ir_mod = env['ir.module.module']

                        # Search for the corresponding module record based on the name (state must be installed)
                        ir_module = ir_mod.search([('name', '=', module), ('state', '=', 'installed')])
                        if not ir_module:
                            return ir_mod.response(
                                'Module with the name {} does not exist, or is not installed'.format(module), 401)

                        # Search for model IDs that correspond to this module
                        model_ids = env['ir.model.data'].search(
                            [('module', '=', ir_module.name), ('model', '=', 'ir.model')]).mapped('res_id')
                        if not model_ids:
                            return ir_mod.response(
                                'Module with the name {} does not have any models to reload'.format(module), 401)

                        names_to_reload = []
                        # Search for actual ir.model records, and check base constraints
                        names = env['ir.model'].search(
                            [('id', 'in', model_ids), ('model', 'not in', models_to_exclude)]).mapped('model')

                        # If model names are passed, check whether they actually exist
                        if model_names:
                            for model_name in model_names:
                                if model_name in names:
                                    names_to_reload.append(model_name)
                                else:
                                    return ir_mod.response(
                                        'Module with the name {} does not contain model with the name {}'.format(
                                            module, model_name), 401)
                        else:
                            names_to_reload = names

                        # Initiate models with env, and reload them
                        model_recs = []
                        for x in names_to_reload:
                            try:
                                with_env = env[x]
                                if not with_env._abstract:
                                    model_recs.append(with_env)
                            except KeyError:
                                pass

                        for model in model_recs:
                            try:
                                model = model.with_context(todo=[], module=module)
                                model._auto_init()
                                model.init()
                                model._auto_end()
                            except KeyError:
                                pass
                    except Exception:
                        odoo.modules.reset_modules_state(db_name)
                        raise
                    return ir_mod.response('Success', 200)
                except Exception as exc:
                    _logger.exception('Failed to load registry tables. Exception - %s' % exc.args[0])
                    del registry_cls.registries[db_name]
