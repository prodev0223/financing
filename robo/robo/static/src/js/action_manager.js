robo.define('robo.ActionManager', function (require) {
    "use strict";


    var ActionManager = require('web.ActionManager');
    var framework = require('web.framework');

    ActionManager.include({
        actions_to_destroy: [],
        ir_actions_act_close_wizard_and_reload_kanban: function (action, options) {
            if (!this.dialog) {
                options.on_close();
            }
            this.dialog_stop();
            var act_view_type = this.inner_widget.active_view.type;
            var inner_widget_controller = this.inner_widget.views[act_view_type].controller;
            if (inner_widget_controller.do_reload) {
                var def = inner_widget_controller.do_reload();
                return $.when(def);
            }
            return $.when();
        },
        ir_actions_act_close_wizard_and_reload_view: function (action, options) {
            if (!this.dialog) {
                options.on_close();
            }
            this.dialog_stop();
            var act_view_type = this.inner_widget.active_view.type;
            var inner_widget_controller = this.inner_widget.views[act_view_type].controller;
            if (inner_widget_controller.reload) {
                var def = inner_widget_controller.reload();
                return $.when(def);
            }
            return $.when();
        },
        history_back_view: function(action, index, max_depth){
           var self = this;
           if (index >= 0){
               //if select_action fails, we have to remember last action active (we redraw html if current_action != prev_action)
               var last_action = self.inner_action;
               var last_widget = self.inner_widget;
               var action_index = self.action_stack.indexOf(action);
               var actions_to_destroy= self.action_stack.slice(action_index + 1); //not splice!

               return this.select_action(action, index, last_action).then(
                    // success
                    function(){
                        return $.Deferred().promise();
                    },
                    //fail
                    function(){
                        self.inner_action = last_action;
                        self.inner_widget = last_widget;
                        //after fail, remember actions not removed in a standard way
                        self.actions_to_destroy= self.actions_to_destroy.concat(actions_to_destroy);
                        return self.history_back_view(action, --index, max_depth);
                    }
                );
           }
           return self.history_back(--max_depth);
        },
        history_back: function(max_depth) {
            var self = this;

            if (max_depth !== undefined && max_depth <= 0){
                return $.Deferred().reject();
            }

            var nb_views = this.inner_action.get_nb_views();
            if (nb_views > 1) {
                // Stay on this action, but select the previous view
                // return this.select_action(this.inner_action, nb_views - 2);
                return self.history_back_view(this.inner_action, nb_views - 2, max_depth || this.action_stack.length-1);
            }
            if (this.action_stack.length > 1) {
                // Select the previous action
                var action = this.action_stack[this.action_stack.length - 2];
                nb_views = action.get_nb_views();
                return self.history_back_view(action, nb_views-1, max_depth || this.action_stack.length-1);
            }
            return $.Deferred().reject();
        },
        clear_action_stack: function() {
            _.map(this.actions_to_destroy, function(action) {
                action.destroy();
            });
            this.actions_to_destroy = [];
            this._super.apply(this, arguments);
        },

        do_push_state: function(state){
            if (this.inner_action) {
                var inner_action_descr = this.inner_action.get_action_descr();
                if (inner_action_descr.robo_menu){
                    state.robo_menu_id = inner_action_descr.robo_menu[0] || typeof inner_action_descr.robo_menu == "number" && inner_action_descr.robo_menu
                }
                else if(inner_action_descr.context && inner_action_descr.context.robo_menu_name){
                    state.robo_menu_id = inner_action_descr.context.robo_menu_name;
                }
                else if (inner_action_descr.context && inner_action_descr.context.force_back_menu_id){
                    state.force_back_menu_id  = inner_action_descr.context.force_back_menu_id;
                }
            }
            this._super(state);
        }


    });

});