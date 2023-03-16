robo.define('robo_dynamic_reports.DynamicInvoiceRegistryReport', function(require) {
    'use strict';
    var core = require('web.core');
    var DynamicReports = require('account_dynamic_reports.DynamicReportController');
    var _t = core._t;

    var DynamicIrMain = DynamicReports.extend({
        widgetModel: 'invoice.registry.dynamic.report',
    });

    core.action_registry.add('dynamic.ir', DynamicIrMain);

});