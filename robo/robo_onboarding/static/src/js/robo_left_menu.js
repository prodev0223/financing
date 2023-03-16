robo.define('robo_onboarding.robo_left_menu', function (require) {
"use strict";

    var LogoMenu = require('robo_theme_v10.logo_menu');
    var Model = require('web.DataModel');

    LogoMenu.include({
        init: function(){
            var self = this;
            $.when(this._super.apply(this, arguments)).then(function () {
                new Model('res.company').call('is_robo_onboarding_shown', {}).then(function (results) {
                    self.show_onboarding = results;
                });
            });
        },
        on_menu_robo_onboarding_process: function(){
            var self = this;
            var action_name = "robo_onboarding.robo_onboarding_tasks_main_user_view_action";
            self.rpc("/web/action/load", { action_id: action_name }).done(function(result) {
                if (_.isObject(result)) {
                    self.do_action(result, {clear_breadcrumbs: true});
                }
            });
        }
    });

});
