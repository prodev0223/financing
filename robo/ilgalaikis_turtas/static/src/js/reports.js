robo.define('ilgalaikis_turtas.reports', function(require) {
"use strict";


var data_manager = require('web.data_manager');
var RoboReports = require('robo.reports');
var session = require('web.session');


return RoboReports.include({
     willStart: function(){
        var self = this;
        this.robo_asset_reports = false;
        return $.when(session.is_premium_manager(), this._super.apply(this, arguments)).then(function(robo_asset_reports){
            self.robo_asset_reports = robo_asset_reports;
            return $.when();
        })
    },
    start: function() {
        this.action_button_mapping["ilgalaikis_turtas.open_assets_report"] = '.robo_button_fixed_assets';
        return this._super();
    },
});

});