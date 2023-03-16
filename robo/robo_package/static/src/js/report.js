robo.define('package.reports', function(require) {
"use strict";


var data_manager = require('web.data_manager');
var RoboReports = require('robo.reports');
var session = require('web.session');


return RoboReports.include({
    willStart: function(){
        var self = this;
        this.robo_package_reports = false;
        return $.when(session.user_has_group('robo_package.robo_package_reports'), this._super.apply(this, arguments)).then(function(robo_package_reports){
            //extend robo.session or call something instead of session.is_manager()
            // self.is_tara_available = is_tara_available;
            self.robo_package_reports = robo_package_reports;
            return $.when();
        })
    },
    start: function() {
        this.action_button_mapping["robo_package.open_package_report_wizard"] = '.robo_button_taros_analysis';
        return this._super();
    },
});

});