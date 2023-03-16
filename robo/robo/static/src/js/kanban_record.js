robo.define('robo.update_kanban', function (require) {
    'use strict';

    // var core = require('web.core');
    // var data = require('web.data');
    // var Dialog = require('web.Dialog');
    // var Model = require('web.Model');
    // var session = require('web.session');

    var core = require('web.core');
    var KanbanRecord = require('web_kanban.Record');
    var KanbanView = require('web_kanban.KanbanView');

    var qweb = core.qweb;


    KanbanView.include({
         render_no_content: function (fragment) {
            var content;
            if (this.options.action.robo_help){
                content = qweb.render('KanbanView.robo_nocontent', {content: this.options.action.robo_help});
            }
            else{
                content = qweb.render('KanbanView.nocontent', {content: this.no_content_msg});
            }
            $(content).appendTo(fragment);
        },
        willStart: function(){
            if (this.fields_view.arch.attrs.multi_open){
                this.multi_open= this.fields_view.arch.attrs.multi_open;
                this.multi_open = _(this.multi_open.split(';')).chain()
                    .compact()
                    .map(function(action_pair) {
                        var pair = action_pair.split(':'),
                            action = pair[0].trim(),
                            expr = pair[1].trim(),
                            field = pair[2].trim();
                        return [action, py.parse(py.tokenize(expr)), expr, field];
                    }).value();
            }
            return this._super.apply(this, arguments);
        },
        render_ungrouped: function (fragment) {
            var self = this;
            var options = _.clone(this.record_options);
            _.extend(options, {multi_open: this.multi_open})
            _.each(this.data.records, function (record) {
                var kanban_record = new KanbanRecord(self, record, options);
                self.widgets.push(kanban_record);
                kanban_record.appendTo(fragment);
            });

            // add empty invisible divs to make sure that all kanban records are left aligned
            for (var i = 0, ghost_div; i < 6; i++) {
                ghost_div = $("<div>").addClass("o_kanban_record o_kanban_ghost");
                ghost_div.appendTo(fragment);
            }
            this.postprocess_m2m_tags();
        },
    });

    KanbanRecord.include({
        init: function(parent, record, options){
            if (options.multi_open){
                this.multi_open = options.multi_open;
            }
            return this._super.apply(this, arguments);
        },
        on_card_clicked: function () {
            if (this.model === 'e.document' && (this.values && this.values.view_id && (typeof this.values.view_id.value === 'object'))) {
                var view_id = this.values.view_id.value[0];

                this.do_action({
                    type: 'ir.actions.act_window',
                    res_model: this.model,
                    res_id: this.id,
                    views: [[view_id, 'form']],
                    target: 'current',
                    context: this.context,
                },{'clear_breadcrumbs': true});
            }else if (this.multi_open instanceof Array){
                var done_once = false;
                for(var i=0, len=this.multi_open.length; i<len && !done_once; ++i) {
                    var pair = this.multi_open[i],
                        action = pair[0],
                        expression = pair[1],
                        field = pair[3],
                        new_id = this.record[field] && (this.record[field].raw_value[0] || this.record[field].raw_value);
                    if (_.isNumber(new_id) && new_id && py.PY_isTrue(py.evaluate(expression, _.mapObject(this.record, function(v,k){return v.raw_value;}) ))) {
                        done_once = true;
                        this.do_action(action, {res_id: new_id});
                    }
                }
                if (!done_once){
                    this._super.apply(this, arguments);
                }
            } else {
                this._super.apply(this, arguments);
            }
        },
    });
});