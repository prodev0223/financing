robo.define('robo.tour', function(require) {
"use strict";

var config = require('web.config');
var session = require('web.session');
var TourManager = require('robo.tourManager');

if (config.device.size_class <= config.device.SIZES.XS) {
    return $.Deferred().reject();
}

return session.is_bound.then(function () {

    var tour = new TourManager(session.robo_tours);

    // Use a MutationObserver to detect DOM changes
    var untracked_classnames = ["o_tooltip", "o_tooltip_content", "o_tooltip_overlay"];
    var check_tooltip = _.debounce(function (records) {
        var update = _.some(records, function (record) {
            return !(is_untracked(record.target)
                || _.some(record.addedNodes, is_untracked)
                || _.some(record.removedNodes, is_untracked));

            function is_untracked(node) {
                var record_class = node.className;
                return (_.isString(record_class)
                    && _.intersection(record_class.split(' '), untracked_classnames).length !== 0);
            }
        });
        if (update) { // ignore mutations which concern the tooltips in untracked_classnames
            tour.update();
        }
    }, 500);
    var observer = new MutationObserver(check_tooltip);

    var start_service = (function () {
        return function (observe) {
            var def = $.Deferred();
            $(function () {
                /**
                 * Once the DOM is ready
                 */
                 _.defer(function () {
                    tour._register_all(observe);
                    if (observe) {
                        observer.observe(document.body, {
                            attributes: true,
                            childList: true,
                            subtree: true,
                        });
                    }
                    def.resolve();
                });

            });
            return def;
        };
    })();

    // Enable the MutationObserver for the robo_tour_user when the DOM is ready and NBR of consumed Tours is not
    start_service(session.is_robo_tour_user);

    return tour;

});

});
