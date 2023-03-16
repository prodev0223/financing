robo.define('robo.RoboEmployees', function (require) {
    "use strict";

    var core = require('web.core');
    var data_manager = require('web.data_manager');
    var ListView = require('web.ListView');
    var RoboTree = require('robo.RoboTree');
    // var Model = require('web.DataModel');
    var session = require('web.session');


    var _t = core._t;
    var QWeb = core.qweb;
    // var list_widget_registry = core.list_widget_registry;

    var RoboTreeEmployees = RoboTree.extend({
        _template: 'RoboListView',
        _templateBox_Manager: 'RoboListEmployeesAbove_Manager',
        _templateBox_User: 'RoboListEmployeesAbove_User',

        start: function(){
            var self = this;
            // var action_new, action_wage_change, action_fire;
            return $.when(

                  session.is_manager(),
                  session.is_user(),
                  // session.user_has_group('robo_basic.group_robo_premium_manager'),
                  // session.user_has_group('robo_basic.group_robo_free_manager'),
                  // session.user_has_group('robo_basic.group_robo_free_employee'),
                  // session.user_has_group('robo_basic.group_robo_premium_user'),


                  // data_manager.load_action("robo.open_employees_action_new"),
                  // data_manager.load_action("e_document.isakymas_del_darbo_uzmokescio_pakeitimo_action"),
                  // data_manager.load_action("e_document.isakymas_del_atleidimo_is_darbo_action"),
                  // data_manager.load_action("robo.open_employee_calendar"),
                  //
                  // data_manager.load_action("e_document.prasymas_del_kasmetiniu_atostogu_action"),
                  // data_manager.load_action("e_document.prasymas_del_tarnybines_komandiruotes_action"),
                  // data_manager.load_action("e_document.prasymas_del_nemokamu_atostogu_suteikimo_action"),

                  this._super.apply(this, arguments)
                  // ).then(function(premium_manager, free_manager, free_employee, premium_user,
                  ).then(function(is_manager, is_user){
                                  // action_new, action_wage_change, action_fire, action_calendar,
                                  // action_pay_holidays, action_trip, action_noPay_holidays){

                    if (is_manager){
                      $(QWeb.render(self._templateBox_Manager, {widget: self})).insertBefore(self.$el);
                      if (self.$el.prev().is('.robo_employees_buttons')){
                        self.$el.prev().on('click', '.employee-box', function(e){
                           var action = $(e.currentTarget).data('xml-id');
                           if (action){
                               self.do_action(action);
                           }
                          //  if ($(e.currentTarget).has('.robo_button_new').length > 0){
                          //      if (action) {
                          //          // action_new.res_id = null;
                          //          // self.do_action(action_new , {replace_last_action: true, 'clear_breadcrumbs': true});
                          //          self.do_action(action);
                          //      }
                          // }
                          // else if ($(e.currentTarget).has('.robo_button_change').length > 0){
                          //      if (action) {
                          //          self.do_action(action_wage_change, {'clear_breadcrumbs': true});
                          //      }
                          // }
                          // else if ($(e.currentTarget).has('.robo_button_fire').length > 0){
                          //      if (_.isObject(action_fire)) {
                          //          self.do_action(action_fire, {'clear_breadcrumbs': true});
                          //      }
                          // }
                          // else if ($(e.currentTarget).has('.robo_button_calendar').length > 0){
                          //      if (_.isObject(action_calendar)) {
                          //          self.do_action(action_calendar, {'clear_breadcrumbs': true, });
                          //      }
                          // }
                        });
                      }
                    }else if (is_user){
                      $(QWeb.render(self._templateBox_User, {widget: self})).insertBefore(self.$el);
                      if (self.$el.prev().is('.robo_employees_buttons')){
                        self.$el.prev().on('click', '.employee-box', function(e){
                           var action = $(e.currentTarget).data('xml-id');
                           if (action){
                               self.do_action(action);
                           }
                          //  if ($(e.currentTarget).has('.robo_button_pay_holiday').length > 0){
                          //      if (_.isObject(action_pay_holidays)) {
                          //          self.do_action(action_pay_holidays, {'clear_breadcrumbs': true});
                          //      }
                          // }
                          // else if ($(e.currentTarget).has('.robo_button_trip').length > 0){
                          //      if (_.isObject(action_trip)) {
                          //          self.do_action(action_trip, {'clear_breadcrumbs': true});
                          //      }
                          // }
                          // else if ($(e.currentTarget).has('.robo_button_noPay_holiday').length > 0){
                          //      if (_.isObject(action_noPay_holidays)) {
                          //          self.do_action(action_noPay_holidays, {'clear_breadcrumbs': true});
                          //      }
                          // }
                          // else if ($(e.currentTarget).has('.robo_button_calendar').length > 0){
                          //      if (_.isObject(action_calendar)) {
                          //          self.do_action(action_calendar, {'clear_breadcrumbs': true});
                          //      }
                          // }
                        });
                      }
                    }
                    self.$el.on('change', '.o_checkbox', function(){
                      var $selected_rows = self.$el.find('tbody tr').has('input:checked');
                      var $not_selected_rows = self.$el.find('tbody tr').has('input:not(:checked)');
                      $selected_rows.toggleClass('selected-row', true);
                      $not_selected_rows.toggleClass('selected-row',false);
                    });
            });
        },
    });

    core.view_registry.add('tree_employees', RoboTreeEmployees);
    return RoboTreeEmployees;
});
