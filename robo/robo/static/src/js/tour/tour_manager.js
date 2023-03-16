robo.define('robo.tourManager', function(require) {
"use strict";

var core = require('web.core');
var local_storage = require('web.local_storage');
var Model = require('web.Model');
var session = require('web.session');
var Tip = require('robo.Tip');

var _t = core._t;

//ROBO: if web_tour is not loaded uncomment this

// $.extend($.expr[':'],{
//     containsExact: function(element, index, matches){
//         return $.trim(element.innerHTML.toLowerCase()) === matches[3].toLowerCase();
//     },
//     containsExactCase: function(element, index, matches){
//         return $.trim(element.innerHTML) === matches[3];
//     },
//     // Note all escaped characters need to be double escaped
//     // inside of the containsRegex, so "\(" needs to be "\\("
//     containsRegex: function(element, index, matches){
//         var regreg =  /^\/((?:\\\/|[^\/])+)\/([mig]{0,3})$/,
//         reg = regreg.exec(matches[3]);
//         return reg ? new RegExp(reg[1], reg[2]).test($.trim(element.innerHTML)) : false;
//     },
//     propChecked: function(element, index, matches) {
//         return $(element).prop("checked") === true;
//     },
//     propSelected: function(element, index, matches) {
//         return $(element).prop("selected") === true;
//     },
//     propValue: function(element, index, matches) {
//         return $(element).prop("value") === matches[3];
//     },
//     propValueContains: function(element, index, matches) {
//         return $(element).prop("value") && $(element).prop("value").indexOf(matches[3]) !== -1;
//     },
// });

function get_step_key(name) {
    return 'tour_' + name + '_step';
}

function get_first_visible_element($elements) {
    for (var i = 0 ; i < $elements.length ; i++) {
        var $i = $elements.eq(i);
        if ($i.is(":visible") && _has_visibility($i)) {
            return $i;
        }
    }
    return $();

    function _has_visibility($elem) {
        if ($elem.css("visibility") === "hidden") {
            return false;
        }
        if ($elem.is("html")) {
            return true;
        }
        return _has_visibility($elem.parent());
    }
}

return core.Class.extend({
    init: function(consumed_tours) {
        this.$body = $('body');
        this.active_tooltips = {};
        this.tours = {};
        this.consumed_tours = consumed_tours || [];
        this.TourModel = new Model('robo.tour');
    },
    /**
     * Registers a tour described by the following arguments (in order)
     * @param [String] tour's name
     * @param [Object] dict of options (optional), available options are:
     *   skip_enabled [Boolean] true to add a link to consume the whole tour in its tips
     * @param [Array] dict of steps, each step being a dict containing a tip description
     */
    register: function() {
        var args = Array.prototype.slice.call(arguments);
        var last_arg = args[args.length - 1];
        var name = args[0];
        if (this.tours[name]) {
            console.warn(_.str.sprintf("Turas %s jau užregistruotas", name));
            return;
        }
        var options = args.length === 2 ? {} : args[1];
        var steps = last_arg instanceof Array ? last_arg : [last_arg];
        var tour = {
            name: name,
            steps: steps,
            only_for: options.only_for || $.when(),
        };
        if (options.skip_enabled) {
            tour.skip_link = '<p><span class="o_skip_tour">' + _t('Panaikinti pagalbą') + '</span></p>';
            tour.skip_handler = function (tip) {
                this._deactivate_tip(tip);
                this._consume_tour(name);
            };
        }
        // //some tours created for special access groups
        // if (options.do_not_register_tour){
        //         return;
        // }
        // console.log(this.tours);
        this.tours[name] = tour;
    },
    _register_all: function (do_update) {
        if (this._all_registered) return;
        this._all_registered = true;

        _.each(this.tours, this._register.bind(this, do_update));
    },
    _register: function (do_update, tour, name) {
        if (tour.ready) return $.when();

        var tour_is_consumed = _.contains(this.consumed_tours, name);

        return tour.only_for.then((function (result) {
            if (result === false) tour_is_consumed = true;
            tour.current_step = parseInt(local_storage.getItem(get_step_key(name))) || 0;
            if (tour_is_consumed || tour.current_step >= tour.steps.length) {
                local_storage.removeItem(get_step_key(name));
                tour.current_step = 0;
            }
            tour.ready = true;

            if (do_update && !tour_is_consumed) {
                this._to_next_step(name, 0);
                this.update(name);
            }
        }).bind(this));
    },
    update: function (tour_name) {
        this.$modal_displayed = $('.modal:visible').last();
        _.each(this.active_tooltips, this._check_for_tooltip.bind(this));

    },
    _check_for_tooltip: function (tip, tour_name) {
        var $trigger;
        if (tip.in_modal !== false && this.$modal_displayed.length) {
            $trigger = this.$modal_displayed.find(tip.trigger);
        } else {
            $trigger = $(tip.trigger);
        }
        var $visible_trigger = get_first_visible_element($trigger);

        var extra_trigger = true;
        var $extra_trigger = undefined;
        if (tip.extra_trigger) {
            $extra_trigger = $(tip.extra_trigger);
            extra_trigger = get_first_visible_element($extra_trigger).length;
        }

        var triggered = $visible_trigger.length && extra_trigger;
        if (triggered) {
            if (!tip.widget) {
                this._activate_tip(tip, tour_name, $visible_trigger);
            } else {
                tip.widget.update($visible_trigger);
            }
            if (typeof tip.animation == 'string'){
                $(tip.trigger).toggleClass(tip.animation, true);
            }
        } else {
            this._deactivate_tip(tip);
        }
    },
    _activate_tip: function(tip, tour_name, $anchor) {
        var tour = this.tours[tour_name];
        var tip_info = tip;
        if (tour.skip_link) {
            tip_info = _.extend(_.omit(tip_info, 'content'), {
                content: tip.content + tour.skip_link,
                event_handlers: [{
                    event: 'click',
                    selector: '.o_skip_tour',
                    handler: tour.skip_handler.bind(this, tip),
                }],
            });
        }
        tip.widget = new Tip(this, tip_info);
        tip.widget.on('tip_consumed', this, this._consume_tip.bind(this, tip, tour_name));
        tip.widget.attach_to($anchor);
    },
    _deactivate_tip: function(tip) {
        if (tip && tip.widget) {
            if (typeof tip.animation == 'string'){
                $(tip.trigger).toggleClass(tip.animation, false);
            }
            tip.widget.destroy();
            delete tip.widget;
        }
    },
    _consume_tip: function(tip, tour_name) {
        this._deactivate_tip(tip);
        this._to_next_step(tour_name);

        if (this.active_tooltips[tour_name]) {
            local_storage.setItem(get_step_key(tour_name), this.tours[tour_name].current_step);
            this.update(tour_name);
        } else {
            this._consume_tour(tour_name);
        }
    },
    _to_next_step: function (tour_name, inc) {
        var tour = this.tours[tour_name];
        tour.current_step += (inc !== undefined ? inc : 1);

        //ROBO: probably we will not use auto property in steps
        var index = _.findIndex(tour.steps.slice(tour.current_step), function (tip) {
            return !tip.auto;
        });

        if (index >= 0) {
            tour.current_step += index;
        } else {
            tour.current_step = tour.steps.length;
        }

        this.active_tooltips[tour_name] = tour.steps[tour.current_step];
    },
    _consume_tour: function (tour_name, error) {
        delete this.active_tooltips[tour_name];
        this.tours[tour_name].current_step = 0;
        local_storage.removeItem(get_step_key(tour_name));

        this.TourModel.call('consume', [[tour_name]]).then((function () {
            this.consumed_tours.push(tour_name);
        }).bind(this));

    },
});
});
