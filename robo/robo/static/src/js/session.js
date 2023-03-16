robo.define('robo.session', function(require) {
    "use strict";
    var session = require('web.session');

    //generate special functions to check rights

    var robo_rights = ['is_manager', 'is_premium_manager', 'is_free_manager',
        'is_accountant', 'is_user', 'is_premium_user', 'is_free_user', 'is_free', 'is_premium',
        'accumulate_statistics', 'get_user_group_ids'];

    var roboRightsFunction = function (method) {
        return function () {
            if (!this.uid) {
                return $.when(false);
            }

            var def = this.rpc('/web/dataset/call_kw/', {
                "model": "res.users",
                "method": method,
                "args": [[this.uid]],
                "kwargs": {}
            });

            return def;
        }.bind(this);
    };
    var defs = [];
    _(robo_rights).map(function (v) {
        defs.push(session[v] = roboRightsFunction.call(session, v));
        return;
    });

    var first_promise = session.is_bound;
    session.is_bound = $.when(first_promise).then(function(){
        return $.when.apply($, defs);
    });

});
