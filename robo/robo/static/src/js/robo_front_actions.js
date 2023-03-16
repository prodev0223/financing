robo.define('robo.roboFrontActions', function (require) {
"use strict";

var core = require('web.core');
var data = require('web.data');
var Dialog = require('web.Dialog');
var framework = require('web.framework');
var pyeval = require('web.pyeval');
var Widget = require('web.Widget');

var QWeb = core.qweb;
var _t = core._t;

var RoboFrontActions = Widget.extend({
    init: function(parent, options) {
        this._super(parent);
        this.sections = [{
                name: 'other',
                label: _t('Veiksmas')
        }];
        this.items = {other: []};
    },
    start: function() {
        var self = this;
        this._super(this);
        this.redraw();
        this.$el.on('click','li a', function(event) {
            var section = $(this).data('section');
            var index = $(this).data('index');
            var item = self.items[section][index];
            if (item.callback) {
                item.callback.apply(self, [item]);
            } else if (item.action) {
                self.on_item_action_clicked(item);
            } else if (item.url) {
                return true;
            }
            event.preventDefault();
        });
    },
    destroy: function() {
        return this._super.apply(this, arguments);
    },
    redraw: function() {
        this.$el.html(QWeb.render('RoboFrontActions', {widget: this}));
        this.$("[title]").tooltip({delay: { show: 500, hide: 0}});
    },
    /**
     * For each item added to the section:
     *
     * ``label``
     *     will be used as the item's name in the sidebar, can be html
     *
     * ``action``
     *     descriptor for the action which will be executed, ``action`` and
     *     ``callback`` should be exclusive
     *
     * ``callback``
     *     function to call when the item is clicked in the sidebar, called
     *     with the item descriptor as its first argument (so information
     *     can be stored as additional keys on the object passed to
     *     ``add_items``)
     *
     * ``classname`` (optional)
     *     ``@class`` set on the sidebar serialization of the item
     *
     * ``title`` (optional)
     *     will be set as the item's ``@title`` (tooltip)
     *
     * @param {String} section_code
     * @param {Array<{label, action | callback[, classname][, title]}>} items
     */
    add_items: function(section_code, items) {
    return $.when(this.session.get_user_group_ids(), items, this).then(function(user_group_ids, items, $self){
        if (items) {
            try {
                var the_view_id = $self.getParent().fields_view.view_id
                if (the_view_id && Number.isInteger(the_view_id)) {
                    items = items.filter(function(item) {
                        return !item.action || (_.isEmpty(item.action.robo_front_view_ids) ||
                        item.action.robo_front_view_ids.includes(the_view_id)) &&
                        (_.isEmpty(item.action.group_ids) ||
                        item.action.group_ids.some(val => user_group_ids.includes(val)));
                    });
                }
            }
            catch(error) {
              // Continue as normal
            }
            $self.items[section_code].unshift.apply($self.items[section_code],items);
            $self.redraw();
        }
        });
    },
    add_toolbar: function(toolbar) {
        var self = this;
        _.each(['action'], function(type) {
            var items = toolbar[type];
            if (items) {
                //only robo_front
                items = _.filter(items, function(action){
                   return action.robo_front;
                });

                var actions = _.map(items, function (item) {
                    return {
                        label: item.name,
                        action: item,
                    };
                });
                self.add_items('other', actions);
            }
        });
    },
    on_item_action_clicked: function(item) {
        var self = this;
        self.getParent().sidebar_eval_context().done(function (sidebar_eval_context) {
            var ids = self.getParent().get_selected_ids();
            var domain;
            if (self.getParent().get_active_domain) {
                domain = self.getParent().get_active_domain();
            }
            else {
                domain = $.Deferred().resolve(undefined);
            }
            if (ids.length === 0) {
                new Dialog(this, {title: _t("Warning"), size: 'medium', $content: $("<div/>").html(_t("You must choose at least one record."))}).open();
                return false;
            }
            var dataset = self.getParent().dataset;
            var active_ids_context = {
                active_id: ids[0],
                active_ids: ids,
                active_model: dataset.model,
            };

            $.when(domain).done(function (domain) {
                if (domain !== undefined) {
                    active_ids_context.active_domain = domain;
                }
                var c = pyeval.eval('context',
                new data.CompoundContext(
                    sidebar_eval_context, active_ids_context));

                self.rpc("/web/action/load", {
                    action_id: item.action.id,
                    context: new data.CompoundContext(
                        dataset.get_context(), active_ids_context).eval()
                }).done(function(result) {
                    result.context = new data.CompoundContext(
                        result.context || {}, active_ids_context)
                            .set_eval_context(c);
                    result.flags = result.flags || {};
                    result.flags.new_window = true;
                    self.do_action(result, {
                        on_close: function() {
                            // reload view
                            self.getParent().reload();
                        },
                    });
                });
            });
        });
    },
});

return RoboFrontActions;

});
