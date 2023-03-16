robo.define('account_dynamic_reports.robo_reports', function(require) {
"use strict";

var RoboReports = require('robo.reports');
var session = require('web.session');

return RoboReports.include({
    willStart: function(){
        var self = this;
        this.robo_dynamic_reports = false;
        return $.when(session.is_premium_manager(), this._super.apply(this, arguments)).then(function(robo_dynamic_reports){
            self.robo_dynamic_reports = robo_dynamic_reports;
            return $.when();
        })
    },
});

});