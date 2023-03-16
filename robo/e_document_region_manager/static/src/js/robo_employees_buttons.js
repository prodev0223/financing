robo.define('e_document_region_manager.list_employees', function(require) {
"use strict";


var data_manager = require('web.data_manager');
var RoboTree = require('robo.RoboTree');
var session = require('web.session');


return RoboTree.include({

     willStart: function(){
        var self = this;
        this.is_region_manager = false;

        return $.when(session.user_has_group('e_document_region_manager.group_e_document_region_manager'),
        this._super.apply(this, arguments)).then(function(is_region_manager){
            self.is_region_manager = is_region_manager;
            return $.when();
        })
    },
    });
});