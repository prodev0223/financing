robo.define('robo_dynamic_reports.DynamicDebtActReport', function(require) {
    'use strict';
    var core = require('web.core');
    var DynamicReports = require('account_dynamic_reports.DynamicReportController');
    var DynamicReportHeaderController = require('account_dynamic_reports.DynamicReportHeaderController');
    var _t = core._t;

    var DynamicDebtActMain = DynamicReports.extend({
        widgetModel: 'debt.act.wizard',
    });


    core.action_registry.add('dynamic.da', DynamicDebtActMain);

});