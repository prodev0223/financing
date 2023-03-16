robo.define('electronics.reports', function(require) {
"use strict";


var data_manager = require('web.data_manager');
var RoboReports = require('robo.reports');
var session = require('web.session');


return RoboReports.include({
     willStart: function(){
        var self = this;
        this.robo_electronics_reports = false;
        return $.when(session.user_has_group('robo_electronics.robo_electronics_reports'), this._super.apply(this, arguments)).then(function(robo_electronics_reports){
            self.robo_electronics_reports = robo_electronics_reports;
            return $.when();
        })
    },
    start: function() {
        this.action_button_mapping["robo_electronics.open_electronics_report_wizard"] = '.robo_button_electronics_analysis';
        this.action_button_mapping["robo_crm.robo_open_crm_profit"] = '.robo_button_crm_profit';
        return this._super();
    },
});

});