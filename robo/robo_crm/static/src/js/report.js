robo.define('robo_crm.reports', function(require) {
"use strict";


var data_manager = require('web.data_manager');
var RoboReports = require('robo.reports');
var session = require('web.session');

return RoboReports.include({
    willStart: function(){
        var self = this;
        this.robo_crm_reports = false;
        return $.when(session.user_has_group('robo_crm.robo_crm_reports'), this._super.apply(this, arguments)).then(function(robo_crm_reports){
            //extend robo.session or call something instead of session.is_manager()
            // self.is_tara_available = is_tara_available;
            self.robo_crm_reports = robo_crm_reports;
            return $.when();
        })
    },
    start: function() {
        this.action_button_mapping["robo_crm.robo_open_crm_activities"] = '.robo_button_crm_activities';
        this.action_button_mapping["robo_crm.robo_open_crm_profit"] = '.robo_button_crm_profit';
        return this._super();
    },
});

});