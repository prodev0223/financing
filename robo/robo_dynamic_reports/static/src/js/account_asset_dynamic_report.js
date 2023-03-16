robo.define('robo_dynamic_reports.DynamicAccountAssetReport', function(require) {
    'use strict';
    var core = require('web.core');
    var DynamicReports = require('account_dynamic_reports.DynamicReportController');
    var _t = core._t;

    var DynamicAaMain = DynamicReports.extend({
        widgetModel: 'account.asset.dynamic.report',
    });

    core.action_registry.add('dynamic.aa', DynamicAaMain);

});