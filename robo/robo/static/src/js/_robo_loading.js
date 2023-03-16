robo.define('robo.RoboLoading', function (require) {
"use strict";

var core = require('web.core');
var framework = require('web.framework');
var session = require('web.session');
var Widget = require('web.Widget');

var _t = core._t;

var RoboLoading = Widget.extend({
    template: "RoboLoading",

    init: function(parent) {
        this._super(parent);
    },
    willstart: function(){
        // framework.blockUI();
        return this._super.apply(this, arguments);
    },
    start: function(){
        return this._super.apply(this, arguments);
    },
    destroy: function(){
        // framework.unblockUI();
        this._super();
    },

});

return RoboLoading;
});

