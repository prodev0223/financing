robo.define('robo_dynamic_reports.DynamicGeneralLedgerReport', function(require) {
    'use strict';
    var core = require('web.core');
    var DynamicReports = require('account_dynamic_reports.DynamicReportController');
    var _t = core._t;

    var DynamicGlMain = DynamicReports.extend({
        widgetModel: 'general.ledger.dynamic.report',
    });

    core.action_registry.add('dynamic.gl', DynamicGlMain);

});