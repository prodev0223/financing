robo.define('robo_dynamic_reports.DynamicAccountingReports', function(require) {
    'use strict';
    var core = require('web.core');
    var QWeb = core.qweb
    var DynamicReports = require('account_dynamic_reports.DynamicReportController');
    var DynamicDataController = require('account_dynamic_reports.DynamicReportDataController');
    var _t = core._t;

    var DynamicAccountingReport = DynamicReports.extend({
        widgetModel: 'accounting.report',
        init: function (view, code) {
            this._super(view, code);
            this.enableReportSettings = false;
        },
    });

    var DynamicPLMain = DynamicAccountingReport.extend({
        accountingReportType: 'profit',
    });

    var DynamicDBARMain = DynamicAccountingReport.extend({
        accountingReportType: 'balance',
    });

    DynamicDataController.include({
        isAccountingReport: function() {
            return this.widgetModel == 'accounting.report';
        },
        setSortByCaret: function() {
            if (this.isAccountingReport()) { return }  // Disable sorting
            return this._super();
        },
        updateSortingOrder: async function(event) {
            if (this.isAccountingReport()) { return }  // Disable sorting
            return this._super(event);
        },
        getTableTemplate: function() {
            if (!this.isAccountingReport()) { return this._super(); }
            return "AccountingReportTable"
        },
        getDataRowTemplate: function() {
            if (!this.isAccountingReport()) { return this._super(); }
            if (this.dynamicReportController.accountingReportType == 'balance') {
                return "AccountingReportGroupDataRow"
            } else {
                return "AccountingReportProfitLossDataRow"
            }
        },
    });

    core.action_registry.add('dynamic.dbar', DynamicDBARMain);
    core.action_registry.add('dynamic.pl', DynamicPLMain);

});