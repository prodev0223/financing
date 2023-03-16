robo.define('robo_stock.reports', function(require) {
"use strict";


var data_manager = require('web.data_manager');
var RoboReports = require('robo.reports');
var session = require('web.session');


return RoboReports.include({

     willStart: function(){
        var self = this;
        this.robo_stock_reports = false;
        return $.when(session.user_has_group('robo_stock.robo_stock_reports'), this._super.apply(this, arguments)).then(function(robo_stock_reports){
            //extend robo.session or call something instead of session.is_manager()
            // self.is_tara_available = is_tara_available;
            self.robo_stock_reports = robo_stock_reports;
            return $.when();
        })
    },
    start: function() {
        this.action_button_mapping["robo_stock.robo_open_current_inventory"] = '.robo_button_stock_store';
        this.action_button_mapping["robo_stock.robo_open_inventory_forecast"] = '.robo_button_stock_forecast';
        this.action_button_mapping["robo_stock.robo_open_inventory_analysis"] = '.robo_button_stock_analysis';
        this.action_button_mapping["robo_stock.robo_open_stock_move_analysis"] = '.robo_button_stock_move_analysis';
        return this._super();
    },
});

});