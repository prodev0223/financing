robo.define('account_dynamic_reports.DynamicReportController', function(require) {
    'use strict';

    var Widget = require('web.Widget');
    var Core = require('web.core');
    var Model = require('web.Model');
    var Session = require('web.session');
    var Framework = require('web.framework');
    var DynamicReportHeaderController = require('account_dynamic_reports.DynamicReportHeaderController')
    var DynamicReportDataController = require('account_dynamic_reports.DynamicReportDataController')
    var _t = Core._t;

    return Widget.extend({
        widgetModel: 'dynamic.report',
        title: _t('Dynamic report'),
        template: 'DynamicReportMain',
        init: function (view, code) {
            this._super(view, code);
            this.wizardId = code.context.wizard_id || code.params.active_id || 0;
            this.title = code.context.title || this.title;
            this.session = Session;
            this.reportHeaderController = null;
            this.reportDataController = null;
            this.uiDisabled = false;
            this.enableReportSettings = true;
        },
        start: function () {
            var self = this;
            return this._super.apply(arguments).then(function () {
                self.initialRender = true;
                if (self.wizardId) { return self.renderWidget() }
                else if (self.widgetModel) {
                    return $.when(self.createNewReport()).then(function () { return self.renderWidget() });
                }
            });
        },
        createNewReport: function() {
            var self = this;
            if (!self.widgetModel) { return }
            return new Model(self.widgetModel).call('create', [{res_model: self.widgetModel},]).then(function (record) {
                self.wizardId = record;
            })
        },
        changeUIState: function(action='enable') {
            (!this.uiDisabled && action !== 'enable') ? Framework.blockUI() : Framework.unblockUI();
            this.uiDisabled = action !== 'enable';
        },
        disableUI: function () { this.changeUIState('disable') },
        enableUI: function () { this.changeUIState('enable') },
        renderWidget: async function () {
            var self = this;
            self.disableUI();
            await Promise.resolve(self.renderHeaderController());
            await Promise.resolve(self.renderDataController());
        },
        refreshData: function () {
            if (!this.reportDataController) { return }
            var self = this;
            this.disableUI()
            this.reportDataController.refreshData().then(function () { self.enableUI() })
        },
        renderHeaderController: function () {
            var node = this.$('.dynamic-report-header-container .py-control-panel');
            node.empty();
            this.reportHeaderController = new DynamicReportHeaderController(this);
            return this.reportHeaderController.appendTo(node);
        },
        renderDataController: function () {
            var node = this.$('.dynamic-report-data-container');
            node.empty()
            this.reportDataController = new DynamicReportDataController(this);
            return this.reportDataController.appendTo(node);
        },
    });

});