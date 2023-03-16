
robo.define('robo_demo.make_blur', function (require) {
"use strict";

    var core = require('web.core');
    var Model = require('web.Model');
    var Widget = require('web.Widget');

    var QWeb = core.qweb;
    var _t = core._t;


    var Make_blur = Widget.extend({
        template: "make_blur",
    });

    core.action_registry.add('make.blur', Make_blur);

return Make_blur;

});
