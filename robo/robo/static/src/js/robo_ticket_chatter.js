robo.define('robo.TicketChatter', function (require) {
"use strict";

var core = require('web.core');
var chatter = require('robo.Chatter');

var _t = core._t;
var QWeb = core.qweb;


var TicketChatter = chatter.extend({
    template: 'robo.TicketChatter',
        events: {
        "click .o_chatter_ticket_button_new_message": "on_open_composer_new_message",
        "click .o_chatter_ticket_button_new_message_client": "on_open_composer_new_client_message",
        "click .o_chatter_ticket_button_new_message_client_ticket": "on_open_composer_new_client_ticket_message",
    },
    _render_value: function () {
        this.allow_posting = this.view.datarecord.allow_posting_widget;
        if (this.allow_posting) {
            $('.o_chatter_ticket_button_new_message').toggleClass('o_form_invisible', false);
        }
        else {$('.o_chatter_ticket_button_new_message').toggleClass('o_form_invisible', true);}
        return this._super.apply(this, arguments);
    },
})

core.form_widget_registry.add('robo_client_ticket_thread', TicketChatter);
return TicketChatter;

});
