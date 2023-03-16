robo.define('RoboOnboardingStatusBar', function (require) {
    "use strict";

    var core = require('web.core');
    var Model = require('web.DataModel');
    var Widget = require('web.Widget');

    var RoboOnboardingStatusBar = Widget.extend({
        template: "RoboOnboardingStatusBar",
        events: {
        },
        willStart: function () {
            return $.when(this.get_progress_data()).then();
        },
        start: function () {
            var self=this;
            $.when(this._super.apply(this, arguments)).then(function () {
                setTimeout(function() {
                    self.update_robo_onboarding_progress(self.robo_onboarding_completion_percentage);
                }, 1000);
            });
        },
        filter_completed_data: function(robo_onboarding_data, completed=true) {
            var good_data = new Array();
            for (var j = 0; j < robo_onboarding_data.length; j++) {
                var data_line = robo_onboarding_data[j];
                if (data_line['completed'] == completed) {
                    good_data.push(data_line);
                }
            }
            return good_data;
        },
        get_progress_data: function() {
            var self = this;
            return $.when(new Model('robo.onboarding.category').call('get_robo_onboarding_progress_data', {}).then(function (results) {
                self.robo_onboarding_tasks_completed = results['completed'];
                self.robo_onboarding_tasks_total = results['total'];
                self.robo_onboarding_completion_percentage = parseInt(Math.floor(results['completed_weight'] / results['total_weight'] * 100.0));
            }));
        },
        update_robo_onboarding_progress: function(onboarding_percentage) {
            var progress_bar = $('div.robo_onboarding_progress_bar div.progress-bar');
            if (Boolean(progress_bar)) {
                progress_bar.toggleClass('no_onboarding_progress', onboarding_percentage == 0);
                progress_bar.attr({'aria-valuenow': onboarding_percentage});
                progress_bar.attr({'style': 'width: '+onboarding_percentage+'%'});
                progress_bar.find('span').replaceWith('<span>'+onboarding_percentage+'%</span>');
            }
        },
    });
    core.action_registry.add('robo_onboarding.RoboOnboardingStatusBar', RoboOnboardingStatusBar);

});