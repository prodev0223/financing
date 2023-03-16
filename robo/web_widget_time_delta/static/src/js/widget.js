robo.define('web.web_widget_time_delta', function(require) {
    "use strict";

    var core = require('web.core');
    var widget = require('web.form_widgets');
    var list_widget_registry = core.list_widget_registry;
    var Model = require('web.Model');



    var FieldTimeDelta = widget.FieldChar.extend({
        template: 'FieldTimeDelta',
        widget_class: 'oe_form_field_time_delta',



        _check: function() {

            var self = this;

            var map_model = new Model(this.view.dataset.model);

            this.mask_humanize = undefined;
            this.showDays = false;
            this.showSeconds = false;

            if ("mask_humanize_string" in this.options) {
                this.mask_humanize = this.options["mask_humanize_string"];
            }

            if ("mask_humanize_field" in this.options) {
                var field_name = self.options["mask_humanize_field"];
                this.mask_humanize = self.view.datarecord[field_name];
            }


            var mask_picker = "";
            if ("mask_picker_string" in this.options) {
                mask_picker = this.options["mask_picker_string"];

                if (mask_picker === "day_second"){
                    this.showDays = true;
                    this.showSeconds = true;
                }
                if (mask_picker === "day"){
                    this.showDays = true;
                }
                if (mask_picker === "second"){
                    this.showSeconds = true;
                }
            }

            if ("mask_picker_field" in this.options) {
                // mask_picker = this.recordData[this.options["mask_picker_field"]];

                var field_name_mask = self.options["mask_picker_field"];
                mask_picker = self.view.datarecord[field_name_mask];

                if (mask_picker === "day_second"){
                    this.showDays = true;
                    this.showSeconds = true;
                }
                if (mask_picker === "day"){
                    this.showDays = true;
                }
                if (mask_picker === "second"){
                    this.showSeconds = true;
                }
            }


        },


        // init: function () {
        //
        //     this._super.apply(this, arguments);
        //     this.mask_humanize = undefined;
        //     this.showDays = false;
        //     this.showSeconds = false;
        //
        //     if ("mask_humanize_string" in this.options) {
        //         this.mask_humanize = this.options["mask_humanize_field"];
        //     }
        //
        //     if ("mask_humanize_field" in this.options) {
        //         this.mask_humanize = this.recordData[this.options["mask_humanize_string"]];
        //     }
        //
        //     var mask_picker = "";
        //     if ("mask_picker_string" in this.nodeOptions) {
        //         mask_picker = this.nodeOptions["mask_picker_string"];
        //
        //         if (mask_picker === "day_second"){
        //             this.showDays = true;
        //             this.showSeconds = true;
        //         }
        //         if (mask_picker === "day"){
        //             this.showDays = true;
        //         }
        //         if (mask_picker === "second"){
        //             this.showSeconds = true;
        //         }
        //     }
        //
        //     if ("mask_picker_field" in this.nodeOptions) {
        //         mask_picker = this.recordData[this.nodeOptions["mask_picker_field"]];
        //
        //         if (mask_picker === "day_second"){
        //             this.showDays = true;
        //             this.showSeconds = true;
        //         }
        //         if (mask_picker === "day"){
        //             this.showDays = true;
        //         }
        //         if (mask_picker === "second"){
        //             this.showSeconds = true;
        //         }
        //     }
        //
        // },


        is_syntax_valid: function () {
            var $input = this.$('input');
            if (!this.get("effective_readonly") && $input.size() > 0) {
                var val = $input.val();
                var isOk = /^\d+$/.test(val);
                if (!isOk) {
                    return false;
                }
                try {
                    this.parse_value(this.$('input').val(), '');
                    return true;
                } catch (e) {
                    return false;
                }
            }
            return true;
        },
        store_dom_value: function() {
            if (!this.silent) {
                if (!this.get('effective_readonly') &&
                    this.$('input').val() !== '' &&
                    this.is_syntax_valid()) {
                    // We use internal_set_value because we were called by
                    // ``.commit_value()`` which is called by a ``.set_value()``
                    // itself called because of a ``onchange`` event
                    this.internal_set_value(
                        this.parse_value(
                            parseInt(this.$('input').val(), 10))
                        );
                }
            }
        },
        //We must make it similar to the float widget, because "var result = field.set_value(self.datarecord[f] || false);"
        // in the form_view widget writes false to input field, but we want 0;
        // Ingeger -> widget as Char -> show false as 0
        set_value: function(value_) {
            if (value_ === false || value_ === undefined) {
                value_ = 0;
            }
            this._super(value_);
        },
        render_value: function () {

            this._check();


            var show_value = parseInt(this.get('value'), 10);

            if (!this.get("effective_readonly")) {
                var $input = this.$el.find('input');
                $input.val(show_value);

                var self = this;
                $input.durationPicker({
                    showSeconds: self.showSeconds,
                    showDays:  self.showDays,
                    onChanged: function (newVal) {
                        $input.val(newVal);
                    },
                    translations: {
                        day: 'diena',
                        hour: 'valanda',
                        minute: 'minutė',
                        second: 'sekundė',
                        days: 'dienos',
                        hours: 'valandos',
                        minutes: 'minutės',
                        seconds: 'sekundės'
                    },
                });

            } else {
                this.$(".oe_form_char_content").text(humanizeDuration(show_value*1000, {language:'lt'}));
            }


        }
    });


    var FieldTimeDeltaList = list_widget_registry.get('field').extend({

        _format: function (row_data, options) {

            var value = row_data[this.id].value;

            if (value === 0){
                return "-"
            }

            var total = parseInt(value, 10);

            return humanizeDuration(total*1000, {language:'lt'})
        }

   });



    list_widget_registry.add('field.time_delta', FieldTimeDeltaList);
    core.form_widget_registry.add('time_delta', FieldTimeDelta);


    return {
        FieldTimeDelta: FieldTimeDelta
    };
});
