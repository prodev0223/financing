robo.define('RoboOnboardingMain', function (require) {
    "use strict";

    var core = require('web.core');
    var Model = require('web.DataModel');
    var Widget = require('web.Widget');
    var session = require('web.session');

    var _t = core._t;

    var RoboOnboarding = Widget.extend({
        template: "RoboOnboarding",
        events: {
            "click li.robo_onboarding_task.robo_onboarding_has_action": "open_robo_onboarding_action",
        },
        willStart: function () {
            return $.when(this.get_onboarding_data(), this.get_progress_data()).then();
        },
        start: function () {
            var self=this;
            $.when(this._super.apply(this, arguments)).then(function () {
                self.update_robo_onboarding_progress_report(
                    self.robo_onboarding_tasks_completed,
                    self.robo_onboarding_tasks_total
                );
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
        get_onboarding_data: function() {
            var self = this;
            return $.when(session.user_has_group('robo_basic.group_robo_premium_accountant')).then(function(accountant){
                    if (accountant){
                        self.show_comments = true;
                    }
                    return $.when(new Model('robo.onboarding.category').call('get_onboarding_data', {})).then(function (results) {
//                        var completed_data = self.filter_completed_data(results);
//                        var not_completed_data = self.filter_completed_data(results, false);
//                        completed_data = self.sort_onboarding_data(completed_data);
//                        not_completed_data = self.sort_onboarding_data(not_completed_data);
//                        self.onboarding_data = not_completed_data.concat(completed_data);
                        self.onboarding_data = results;
                    });
                });
        },
        get_progress_data: function() {
            var self = this;
            return $.when(new Model('robo.onboarding.category').call('get_robo_onboarding_progress_data', {}).then(function (results) {
                self.robo_onboarding_tasks_completed = results['completed'];
                self.robo_onboarding_tasks_total = results['total'];
                self.robo_onboarding_completion_percentage = parseInt(results['completed_weight'] / results['total_weight'] * 100.0).toFixed(2);
            }));
        },
        open_robo_onboarding_action: function(event) {
            var closest_li = event.target.closest('li');
            if (Boolean(closest_li)) {
                var action_to_call = closest_li.getAttribute('onboarding_action');
                var url_to_call = closest_li.getAttribute('onboarding_url_link');
                if (Boolean(action_to_call) && action_to_call != "false") {
                    var self = this;
                    self.rpc("/web/action/load", { action_id: action_to_call }).done(function(result) {
                        if (_.isObject(result)) {
                            self.do_action(result, {clear_breadcrumbs: true});
                        }
                    });
                } else if (Boolean(url_to_call) && url_to_call != "false") {
                    window.open(url_to_call, "_blank");
                }
            }
        },
        sort_onboarding_data: function(data_to_be_sorted, sort_by='sequence') {
            if (!['sequence', 'completed'].includes(sort_by)) {
                return data_to_be_sorted
            }

            var key_sequence_pairs = Object.keys(data_to_be_sorted).map(function(key) {
                return [key, data_to_be_sorted[key][sort_by]];
            });

            if (sort_by == 'sequence') {
                key_sequence_pairs.sort(function(first, second) {
                    return first[1] - second[1];
                });
            } else {
                key_sequence_pairs.sort(function(first, second) {
                    return (first[1] === second[1])? 0 : second[1]? -1 : 1;
                });
            }
            var sorted_dictionary_data = new Array();
            for (var j = 0; j < key_sequence_pairs.length; j++) {
                sorted_dictionary_data.push(data_to_be_sorted[parseInt(key_sequence_pairs[j][0])]);
            }
            return sorted_dictionary_data;
        },
        update_robo_onboarding_progress: function(onboarding_percentage) {
            var progress_bar = $('div.robo_onboarding_progress_bar div.progress-bar');
            if (Boolean(progress_bar)) {
                if (onboarding_percentage == 0) {
                    progress_bar.toggleClass('no_onboarding_progress', true);
                } else {
                    progress_bar.toggleClass('no_onboarding_progress', false);
                }
                onboarding_percentage = Math.floor(onboarding_percentage);
                progress_bar.attr({'aria-valuenow': onboarding_percentage});
                progress_bar.attr({'style': 'width: '+onboarding_percentage+'%'});
                progress_bar.find('span').replaceWith('<span>'+onboarding_percentage+'%</span>');
            }
        },
        update_robo_onboarding_progress_report: function(tasks_completed, tasks_total) {
            var progress_report_span = $(this.el).find('div.onboarding_status_container span.onboarding_progress_report');
            if (Boolean(progress_report_span)) {
                var completion_text = '<span>' + _t('Completed ') + tasks_completed.toString() + _t(' out of ') +
                                        tasks_total.toString() + _t(' steps.') + '</span>'
                $(completion_text).appendTo(progress_report_span);
            }
        },
    });
    core.action_registry.add('robo_onboarding.RoboOnboarding', RoboOnboarding);

});