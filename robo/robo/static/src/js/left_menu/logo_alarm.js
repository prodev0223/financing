robo.define('robo_theme_v10.logo_alarm', function (require) {
"use strict";

    var bus = require('bus.bus').bus;
    var chat_manager = require('mail.chat_manager');
    var core = require('web.core');
    var Model = require('web.DataModel');
    var RoboTree = require('robo.RoboTree');
    var UserMenu = require('web.UserMenu');
    var utils = require('web.utils');
    var Widget = require('web.Widget');

    var QWeb = core.qweb;



var LogoAlarm = Widget.extend({
    template: 'LogoBell',
    template_message: 'MessageTemplate',
    events: {
        "click .dropdown-toggle": 'on_bell_click',
        "click .o_all_messages": 'on_showAll_click',
        "click .o_mail_messsage_preview": "on_message_click",
        "click .o_read_all_messages": "on_readAll_click",
        "click": 'on_click',
    },
    init: function(){
      this.dropPrevious = new utils.DropPrevious();
      this.unread_messages = 0;
      this.messages_to_show = [];
      this.mailModel = new Model('mail.message');
      this._super.apply(this, arguments);
    },
    start: function () {
        var self = this;
        this.$messages_preview = this.$('.o_mail_navbar_dropdown_messages');
        bus.on('notification', this, function (notifications) {
            _.each(notifications, (function (notification) {
                if (notification[0][1] === 'robo.message') {
                    this.update_counter(notification[1]);
                }
            }).bind(this));
        });
        this.$('.dropdown-menu').parent().on('show.bs.dropdown', function(){
            self.trigger_up('child_element_clicked');
            self.update_message_preview();
        });
        return $.when(this.update_counter()).then(function(){
            return self._super()
        });
    },
    update_counter: function () {
        //session is already bounded
        var self = this;
        this.rpc('/robomessage/needaction').then(function(counter){
            self.$('.robo-logo-alarm').toggleClass('o_notification_alarm', Boolean(counter));
            self.$('.robo-logo-alarm').toggleClass('animated', Boolean(counter));
            self.unread_messages = counter;
            self.$('.count_messages').text(counter);
        });
    },
    update_message_preview: function(){
        var self = this;
        // Display spinner while waiting for channels preview
        this.$messages_preview.html(QWeb.render('Spinner'));
        self.dropPrevious.add(self.rpc('/robomessage/lastmessages')).then(function(result){
                    if (_.isArray(result)) {
                        self.messages_to_show = result;
                    }
                    var messages_html = QWeb.render(self.template_message, {messages: result, unread_counter: self.unread_messages});
                    self.$messages_preview.html(messages_html);
                });
    },
    /* 1. check if we have rec_id, rec_model;
       2. if not 1, check if we have act_id
       3. if not 2, open all messages
     */
    on_message_click: function(e){
        //open message link
        var self = this;
        e.stopPropagation();
        e.preventDefault();
        if (_.isArray(this.messages_to_show)){
            var message_id = $(e.currentTarget).data('id')
            var message = _(this.messages_to_show).find(function(r){
                return r.id == message_id
            });

            var action = {
                type: 'ir.actions.act_window',
                res_model: message.rec_model,
                res_id: message.rec_id,
                views: [[_.isNumber(message.view_id)?message.view_id:false , 'form']],
                target: 'current',
            };
            self.mailModel.call('set_roboFrontMessage_done',[[message_id]]).then(function(){
                if (_.isString(message.rec_model) && message.rec_model.length>0
                    && _.isNumber(message.rec_id) && message.rec_id>0) {
                    self.do_action(action, {'clear_breadcrumbs': true});
                }
                else if (_.isNumber(message.action_id) && message.action_id>0
                        && _.isNumber(message.rec_id)){
                    if (message.rec_id > 0) {
                        self.do_action(message.action_id, {'clear_breadcrumbs': true, res_id: message.rec_id, view_type: 'form'});
                    }
                    else{
                        self.do_action(message.action_id, {'clear_breadcrumbs': true});
                    }
                }
                else{
                    self._showAll_act();
                }
            });
            //close popover
            this.$('.dropdown-toggle').dropdown('toggle');
        }
    },
    on_showAll_click: function(e){
      //open treeview
        e.stopPropagation();
        e.preventDefault();
        this._showAll_act();
        //close popover
        this.$('.dropdown-toggle').dropdown('toggle');
    },
    on_readAll_click: function(e){
        //read all messages
        e.stopPropagation();
        e.preventDefault();
        this.mailModel.call('set_AllRoboFrontMessage_done');
        //close popover
        this.$('.dropdown-toggle').dropdown('toggle');
    },
    on_click: function(e){
        //turn off all event bubbles
        e.stopPropagation();
    },
    on_bell_click: function(e){
        e.stopPropagation();
        e.preventDefault();
        this.$('.dropdown-toggle').dropdown('toggle');
    },
    _showAll_act: function(){
        this.do_action('robo.all_frontMessages_act', {'clear_breadcrumbs': true});
    },
    // on_click: function(e){
    //     e.stopPropagation();
    //     e.preventDefault();
    //     // this.$('a[data-toggle]').dropdown('toggle');
    //     this.showWaitingDocuments();
    // },
    // showWaitingDocuments: function () {
    //     var self = this;
    //     this.do_action('e_document.e_document_action', {clear_breadcrumbs: true}).then(function () {
    //         self.trigger_up('hide_app_switcher');
    //     });
    // },
});

var MessagesMultipleFormTree = RoboTree.extend({

        do_activate_record: function (index, id, dataset, view) {
            var self = this;

            this.dataset.ids = dataset.ids;

            var view_id = this.records.get(id).attributes.view_id,
                rec_id = this.records.get(id).attributes.rec_id,
                rec_model = this.records.get(id).attributes.rec_model,
                action_id = this.records.get(id).attributes.action_id;

            var action = {
                type: 'ir.actions.act_window',
                res_model: rec_model,
                res_id: rec_id,
                views: [[_.isNumber(view_id)?view_id:false, 'form']],
                target: 'current',
                context: dataset.context,
            };

            (new Model('mail.message')).call('set_roboFrontMessage_done',[[id]]).then(function(){
                if (_.isString(rec_model) && rec_model.length>0 && _.isNumber(rec_id) && rec_id>0) {
                    self.do_action(action, {'clear_breadcrumbs': true});
                }
                else if (_.isNumber(action_id) && action_id>0 && _.isNumber(rec_id)){
                    if (rec_id > 0){
                        self.do_action(action_id, {'clear_breadcrumbs': true, res_id: rec_id, view_type: 'form'});
                    }
                    else{
                        self.do_action(action_id, {'clear_breadcrumbs': true});
                    }

                }
            });

        },
    });

    core.view_registry.add('tree_front_messages', MessagesMultipleFormTree);

return LogoAlarm;

});
