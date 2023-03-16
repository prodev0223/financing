robo.define('robo.rekvizitai', function (require) {
    "use strict";

    var common = require('web.form_common');
    var core = require('web.core');
    var Model = require('web.DataModel');
    var utils = require('web.utils');
    var Widget = require('web.Widget');

    var RekvizitaiCompletionFieldMixin = {
        init: function () {
            this.limit = 10;
            this.orderer = new utils.DropMisordered();
            this.dataModel = new Model('res.partner');
        },
        get_search_result: function (search_val) {
            var self = this;
            var def = this.orderer.add(self.dataModel.call('vz_search', [search_val]), {}, {shadow: true});
            return utils.reject_after(def, utils.delay(5000)).then(function (result) {
                // var counter=1;
                var values = _.map(result, function (x) {
                    return {
                        label: x.name,
                        value: x.name,
                        name: x.name,
                        kodas: x.kodas,
                    }
                });
                if (values.length > self.limit) {
                    values = values.slice(0, self.limit);
                }
                return $.Deferred().resolve(values);
            }, function(){
                return $.Deferred().resolve();
            });
        },
    };
    //TODO: catch "Error: cannot call methods on autocomplete prior to initialization;"
    var Rekvizitai = common.AbstractField.extend(RekvizitaiCompletionFieldMixin, common.ReinitializeFieldMixin, {
        template: "Rekvizitai",
        events: {
            'keydown input': function (e) {
                switch (e.which) {
                    case $.ui.keyCode.UP:
                    case $.ui.keyCode.DOWN:
                        e.stopPropagation();
                }
            },
        },
        init: function (field_manager, node) {
            this._super(field_manager, node);
            RekvizitaiCompletionFieldMixin.init.call(this);
            this.current_display = null;
            this.is_started = false;
        },
        reinit_value: function (val) {
            this.internal_set_value(val);
            if (this.is_started && !this.no_rerender) {
                this.render_value();
            }
        },
        //called at start
        initialize_field: function () {
            this.is_started = true;
            core.bus.on('click', this, function () {
                if (!this.get("effective_readonly") && this.$input && this.$input.data('ui-autocomplete') != undefined && this.$input.autocomplete('widget').is(':visible')) {
                    this.$input.autocomplete("close");
                }
            });
            common.ReinitializeFieldMixin.initialize_field.call(this);
        },
        //called after initialize_field or after change effective_readonly
        initialize_content: function () {
            if (!this.get("effective_readonly")) {
                this.render_editable();
            }
        },
        destroy_content: function () {
            if (this.$input) {
                if (this.$input.data('ui-autocomplete')) {
                    this.$input.autocomplete("destroy");
                }
                this.$input.closest(".modal .modal-content").off('scroll');
                this.$input.off('keyup blur autocompleteclose autocompleteopen ' +
                    'focus focusout change keydown');
                delete this.$input;
            }
        },
        destroy: function () {
            this.destroy_content();
            return this._super();
        },
        render_editable: function () {
            var self = this;
            this.$input = this.$("input");
            // some behavior for input
            var input_changed = _.debounce(function () {
                if (self.$input && self.current_display !== self.$input.val()) {
                    if (self.$input.val() === "") {
                        self.internal_set_value(false);
                    } else {
                        self.internal_set_value(self.$input.val());
                    }
                }
            },50);

            this.$input.keydown(input_changed);
            this.$input.change(input_changed);
            this.$input.on('click', function () {
                if (self.$input.autocomplete("widget").is(":visible")) {
                    self.$input.autocomplete("close");
                } else {
                    self.$input.autocomplete("search");
                }
            });

            //ROBO what is it?
            // Autocomplete close on dialog content scroll
            var close_autocomplete = _.debounce(function () {
                if (self.$input.autocomplete("widget").is(":visible")) {
                    self.$input.autocomplete("close");
                }
            }, 50);
            this.$input.closest(".modal .modal-content").on('scroll', this, close_autocomplete);

            var ignore_blur = false;
            this.$input.on({
                // focusout: anyoneLoosesFocus,
                focus: function () {
                    self.trigger('focused');
                },
                autocompleteopen: function () {
                    ignore_blur = true;
                },
                autocompleteclose: function () {
                    setTimeout(function () {
                        ignore_blur = false;
                    }, 0);
                },
                blur: function () {
                    // autocomplete open
                    if (ignore_blur) {
                        $(this).focus();
                        return;
                    }
                    //ROBO When do we need this???
                    if (_(self.getChildren()).any(function (child) {
                            return child instanceof common.ViewDialog;
                        })) {
                        return;
                    }
                    self.trigger('blurred');
                }
            });

            var isSelecting = false;
            // autocomplete
            this.$input.autocomplete({
                source: function (req, resp) {
                    if (req.term && req.term.length > 1) {
                        self.get_search_result(req.term).done(function (result) {
                            resp(result);
                        });
                    }
                    else{
                        if (self.$input.autocomplete("widget").is(":visible")) {
                            self.$input.autocomplete("close");
                        }
                    }
                },
                select: function (event, ui) {
                    isSelecting = true;
                    var item = ui.item;
                    if (item.name && item.kodas) {
                        self.dataModel.call('vz_read_dict',[item.kodas]).then(function(result){
                            self.field_manager.set_values(result);
                        });
                    }
                },
                focus: function (e, ui) {
                    e.preventDefault();
                },
                autoFocus: true,
                html: true,
                // disabled to solve a bug, but may cause others
                //close: anyoneLoosesFocus,
                minLength: 0,
                delay: 650,
            });
            // set position for list of suggestions box
            this.$input.autocomplete("option", "position", {my: "left top", at: "left bottom"});
            // used to correct a bug when selecting an element by pushing 'enter' in an editable list
            this.$input.keyup(function (e) {
                if (e.which === 13) { // ENTER
                    if (isSelecting)
                        e.stopPropagation();
                }
                isSelecting = false;
            });
        },
        render_value: function () {
            var self = this;
            if (!this.get("value")) {
                this.display_string(null);
                return;
            }
            var display = this.get("value");
            if (display) {
                this.display_string(display);
                return;
            }
        },
        display_string: function (str) {
            var noValue = (str === null);
            if (!this.get("effective_readonly")) {
                this.$input.val(noValue ? "" : (str.split("\n")[0].trim() || $(data.noDisplayContent).text()));
                this.current_display = this.$input.val();
            } else {
                this.$el.html(noValue ? "" : (_.escape(str.trim()).split("\n").join("<br/>") || data.noDisplayContent));
            }
        },
        is_false: function() {
            return ! this.get("value");
        },
        focus: function () {
            var input = !this.get('effective_readonly') && this.$input && this.$input[0];
            return input ? input.focus() : false;
        },
        // default set_value is in abstractField object
    });

    core.form_widget_registry.add('rekvizitai', Rekvizitai);

    return RekvizitaiCompletionFieldMixin;

});
