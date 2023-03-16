robo.define('robo.payment', function (require) {
"use strict";

var core = require('web.core');
var form_common = require('web.form_common');
var formats = require('web.formats');
var Model = require('web.Model');

var QWeb = core.qweb;

var ShowPaymentLineWidget = form_common.AbstractField.extend({
    render_value: function() {
        var self = this;
        var info = JSON.parse(this.get('value'));
        var invoice_id = info.invoice_id;
        if (info !== false) {
            _.each(info.content, function(k,v){
                k.index = v;
                k.amount = formats.format_value(k.amount, {type: "float", digits: k.digits});
                if (k.date){
                    k.date = formats.format_value(k.date, {type: "date"});
                }
            });
            this.$el.html(QWeb.render('ShowPaymentInfoRobo', {
                'lines': info.content, 
                'outstanding': info.outstanding, 
                'title': info.title
            }));
            this.$('.outstanding_credit_assign').click(function(){
                var id = $(this).data('id') || false;
                new Model("account.invoice")
                    .call("assign_outstanding_credit", [invoice_id, id])
                    .then(function (result) {
                        self.view.reload();
                    });
            });
            _.each(this.$('.js_payment_info'), function(k, v){
                var options = {
                    'content': QWeb.render('PaymentPopOverRobo', {
                            'name': info.content[v].name, 
                            'journal_name': info.content[v].journal_name, 
                            'date': info.content[v].date,
                            'amount': info.content[v].amount,
                            'currency': info.content[v].currency,
                            'position': info.content[v].position,
                            'payment_id': info.content[v].payment_id,
                            'move_id': info.content[v].move_id,
                            'offsetting_move': info.content[v].offsetting_front_move,
                            'accountant': info.content[v].accountant,
                            'ref': info.content[v].ref,
                            'show': info.content[v].show
                            }),
                    'html': true,
                    'placement': 'left',
                    'title': 'Mokėjimo informacija',
                    'trigger': 'focus',
                    'delay': { "show": 0, "hide": 100 },
                };
                $(k).popover(options);
                $(k).on('shown.bs.popover', function(event){
                    $(this).parent().find('.js_unreconcile_payment').click(function(){
                        var payment_id = parseInt($(this).attr('payment-id'))
                        if (payment_id !== undefined && payment_id !== NaN){
                            new Model("account.invoice")
                                .call("js_unreconcile_payment", [self.view.datarecord.id, payment_id])
                                .then(function (result) {
                                    self.view.reload();
                                });
                        }
                    });
                    $(this).parent().find('.js_unreconcile_offsetting').click(function(){
                        var payment_id = parseInt($(this).attr('payment-id'))
                        if (payment_id !== undefined && payment_id !== NaN){
                            new Model("account.move.line")
                                .call("delete_move_reconcile_offsetting", [payment_id, {'invoice_id': self.view.datarecord.id}])
                                .then(function (result) {
                                    self.view.reload();
                                });
                        }
                    });
                    $(this).parent().find('.js_open_payment').click(function(){
                        var move_id = parseInt($(this).attr('move-id'))
                        if (move_id !== undefined && move_id !== NaN){
                            //Open form view of account.move with id = move_id
                            self.do_action({
                                type: 'ir.actions.act_window',
                                res_model: 'account.move',
                                res_id: move_id,
                                views: [[false, 'form']],
                                target: 'current'
                            });
                        }
                    });
                    $(this).parent().find('.js_delete_payment').click(function(){
                        var payment_id = parseInt($(this).attr('payment-id'))
                        if (payment_id !== undefined && payment_id !== NaN){
                            new Model("account.move.line")
                                .call("delete_move_reconcile", [payment_id])
                                .then(function (result) {
                                    self.view.reload();
                                });
                        }
                    });
                });
            });
        }
        else {
            this.$el.html('');
        }
    },
});

var ShowBankStatementLineWidget = form_common.AbstractField.extend({
    render_value: function() {
        var self = this;
        var info = JSON.parse(this.get('value'));
        var invoice_id = info.invoice_id;
        if (info !== false) {
            _.each(info.content, function(k,v){
                k.index = v;
                k.amount = formats.format_value(k.amount, {type: "float", digits: k.digits});
                if (k.date){
                    k.date = formats.format_value(k.date, {type: "date"});
                }
            });
            this.$el.html(QWeb.render('ShowBankStatementInfoRobo', {
                'lines': info.content,
                'outstanding_statements': info.outstanding_statements,
                'title': info.title
            }));
            this.$('.bank_statement_assign').click(function(){
                var id = $(this).data('id') || false;
                new Model("account.bank.statement.line")
                    .call("assign_bank_statement", [id, invoice_id])
                    .then(function (result) {
                        self.view.reload();
                    });
            });
        }
        else {
            this.$el.html('');
        }
    },
});

var ShowReversePaymentLineWidget = form_common.AbstractField.extend({
    render_value: function() {
        var self = this;
        var info = JSON.parse(this.get('value'));
        var invoice_id = info.invoice_id;
        if (info !== false) {
            _.each(info.content, function(k,v){
                k.index = v;
                k.amount = formats.format_value(k.amount, {type: "float", digits: k.digits});
                if (k.date){
                    k.date = formats.format_value(k.date, {type: "date"});
                }
            });
            this.$el.html(QWeb.render('ShowOffsettingInfoRobo', {
                'lines': info.content,
                'offsetting': info.offsetting,
                'title': info.title
            }));
            this.$('.make_offsetting').click(function(){
                var id = $(this).data('id') || false;
                new Model("account.move.line")
                    .call("js_call_reconcile_different_wizard", [id, invoice_id])
                    .then(function (result) {
                        self.view.reload();
                    });
            });
        }
        else {
            this.$el.html('');
        }
    },
});

core.form_widget_registry.add('robo_payment', ShowPaymentLineWidget);
core.form_widget_registry.add('robo_bank_statement', ShowBankStatementLineWidget);
core.form_widget_registry.add('robo_offsetting', ShowReversePaymentLineWidget);

});