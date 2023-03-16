robo.define('gpais.reports', function(require) {
"use strict";


var data_manager = require('web.data_manager');
var RoboReports = require('robo.reports');
var session = require('web.session');


return RoboReports.include({

     willStart: function(){
        var self = this;
        this.robo_gpais_reports = false;
        return $.when(session.user_has_group('robo_electronics.robo_electronics_reports'), this._super.apply(this, arguments)).then(function(robo_gpais_reports){
            self.robo_gpais_reports = robo_gpais_reports;
            return $.when();
        })
    },
    start: function() {
        this.action_button_mapping["robo_gpais.open_gpais_wizard"] = '.robo_button_gpais';
        return this._super();
    },
});

});