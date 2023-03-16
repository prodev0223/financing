robo.define('robo.form_widgets', function (require) {
"use strict";

var common = require('web.form_common');
var config = require('web.config');
var core = require('web.core');
var data = require('web.data');
var form_widgets = require('web.form_widgets');
var session = require('web.session');
require('web_editor.backend');


// var Button = core.form_tag_registry.get('button');
var QWeb = core.qweb;



var RoboFormButton = common.FormWidget.extend({
    template: 'WidgetButton.RoboFormActionButton',
    init:function(field_manager, node){
        node.attrs.type = node.attrs['data-button-type'];
        this._super(field_manager, node);
        this.string = (this.node.attrs.string || '').replace(/_/g, '');
        if (JSON.parse(this.node.attrs.default_focus || "0")) {
            // TODO fme: provide enter key binding to widgets
            this.view.default_focus_button = this;
        }
        this.force_disable = false;
        this.view.on('update_robo_buttons', this, this.check_disable);
    },
    check_disable: function(){
        var disabled = !(this.view.get("actual_mode") === "view");
        this.force_disable = disabled;
        this.$el.prop('disabled', disabled);
    },
     start: function() {
        this.$el.prop('disabled', this.force_disable);
        this._super.apply(this, arguments);
        this.$el.on('click', this.on_click);
        if (this.node.attrs.help || session.debug) {
            this.do_attach_tooltip();
        }
        this.setupFocus(this.$el);
    },
    on_click: function(){
        //rewrite;
    }
});
var DButton = RoboFormButton.extend({
    on_click: function(){
        this.view.on_button_delete();
    }
});

var DuplButton = RoboFormButton.extend({
    on_click: function(){
        this.view.on_button_duplicate();
    }
});

form_widgets.FieldStatus.include({
    template: undefined,
    className: "o_statusbar_status",
    render_value: function() {
        var self = this;
        // var $content = $(QWeb.render("FieldStatus.content." + ((config.device.size_class <= config.device.SIZES.XS)? 'mobile' : 'desktop'), {
        var $content = $(QWeb.render("FieldStatus.content.mobile", {
            'widget': this,
            'value_folded': _.find(this.selection.folded, function (i) {
                return i[0] === self.get('value');
            }),
        }));
        this.$el.empty().append($content.get().reverse());
    },
    bind_stage_click: function () {
        this.$el.on('click','button[data-id]',this.on_click_stage);
    },
});

var FieldPhone = form_widgets.FieldEmail.extend({
    prefix: 'tel',
    init: function() {
        this._super.apply(this, arguments);
        this.clickable = config.device.size_class <= config.device.SIZES.XS;
    },
    render_value: function() {
        this._super();
        if(this.clickable) {
            // Split phone number into two to prevent Skype app from finding it
            var text = this.$el.text();
            var part1 = _.escape(text.substr(0, text.length/2));
            var part2 = _.escape(text.substr(text.length/2));
            this.$el.html(part1 + "&shy;" + part2);
        }
    }
});

var FieldHTML = core.form_widget_registry.get('html');

var FieldPayslipNote = FieldHTML.extend({
    start: function(){
        var self = this;
        this.$el.on('click','td a.o_payslip_note, td a.o_payslip', function(e){
            e.stopPropagation();
            var $target = $(e.currentTarget),
              field = $target.data('id'), //ROBO: not good naming, but only id available to pass values....
              $row = $target.closest('tr'),
              record_id = $row.data('id');

            if ($target.attr('disabled')) {
                return;
            }
            $target.attr('disabled', 'disabled');

            return self.field_manager.do_execute_action(
                {
                    type: 'object',
                    name: field,
                },
                new data.DataSetStatic(null, self.field.__attrs.model, {}, []), // ids=[]
                record_id, // record_id
                function(){
                    $target.removeAttr('disabled');
                }// on_close
            );

        });
      return this._super.apply(this, arguments);
    }
});

var FieldRoboRadio = common.AbstractField.extend(common.ReinitializeFieldMixin, {
    template: 'FieldRoboRadio',
    events: {
        'click label.btn-robo-radio-toggle.active_link': 'click_change_value'
    },
    init: function(field_manager, node) {
        /* Radio button widget: Attributes options:
        * - "horizontal" to display in column
        */
        this._super(field_manager, node);
        this.selection = _.clone(this.field.selection) || [];
        this.domain = false;
        this.uniqueId = _.uniqueId("radio");
    },
    initialize_content: function () {
        this.field_manager.on("view_content_has_changed", this, this.get_selection);
        this.get_selection();
    },
    click_change_value: function (event) {
        event.stopPropagation();
        event.preventDefault();
        var val = $(event.currentTarget).attr('value');
        val = this.field.type == "selection" ? val : +val;
        if (val !== this.get_value()) {
            this.set_value(val);
        }
    },
    /** Get the selection and render it
     *  selection: [[identifier, value_to_display], ...]
     *  For selection fields: this is directly given by this.field.selection
     *  For many2one fields:  perform a search on the relation of the many2one field
     */
    get_selection: function() {
        var self = this;
        var selection = [];
        var def = $.Deferred();
        if (self.field.type == "selection") {
            selection = self.field.selection || [];
            def.resolve();
        }
        return def.then(function () {
            if (!_.isEqual(selection, self.selection)) {
                self.selection = _.clone(selection);
                self.renderElement();
                self.render_value();
            }
        });
    },
    set_value: function (value_) {
        if (this.field.type == "selection") {
            value_ = _.find(this.field.selection, function (sel) { return sel[0] == value_;});
        }

        this._super(value_);
    },
    get_value: function () {
        var value = this.get('value');
        value = ((value instanceof Array)? value[0] : value);
        return  _.isUndefined(value) ? false : value;
    },
    // render_value: function () {
    //     var self = this;
    //     if(this.get('effective_readonly')) {
    //         this.$el.html(this.get('value')? this.get('value')[1] : "");
    //     } else {
    //         this.$("input").prop("checked", false).filter(function () {return this.value == self.get_value();}).prop("checked", true);
    //     }
    // }
});


core.form_tag_registry.add('button_d', DButton);
core.form_tag_registry.add('button_dupl', DuplButton);
core.form_widget_registry
    .add('phone', FieldPhone)
    .add('payslip_note', FieldPayslipNote)
    .add('robo_radio', FieldRoboRadio);
    // .add('upgrade_boolean', form_widgets.FieldBoolean) // community compatibility
    // .add('upgrade_radio', form_widgets.FieldRadio); // community compatibility

});

