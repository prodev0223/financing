robo.define('robo.fieldBinary', function (require) {
    "use strict";

    var core = require('web.core');
    var crash_manager = require('web.crash_manager');
    var FieldBinaryFile = core.form_widget_registry.get('binary');
    var framework = require('web.framework');
    var utils = require('web.utils');

    FieldBinaryFile.include({

        initialize_field: function () {
            this.upload_file_name = this.node.attrs.filename && this.view.datarecord[this.node.attrs.filename];
            this.upload_file_mime = this.node.attrs.filemime && this.view.datarecord[this.node.attrs.filemime];
            this._super.apply(this, arguments);
        },
        on_file_uploaded_and_valid: function (size, name, content_type, file_base64) {
            this.upload_file_name = name;
            this.upload_file_mime = content_type;
            this._super.apply(this, arguments);
            this.set_filemime(content_type);
        },
        set_filename: function (value) {
            var filename = this.node.attrs.filename;
            if (!!filename) {
                var field = this.field_manager.fields[filename];
                if (!!field) {
                    field.set_value(value);
                    field._dirty_flag = true;
                }
            }
        },
        set_filemime: function (value) {
            var filemime = this.node.attrs.filemime;
            if (!!filemime) {
                var field = this.field_manager.fields[filemime];
                if (!!field) {
                    field.set_value(value);
                    field._dirty_flag = true;
                }
            }
        },
        render_value: function () {
            var filename = this.view.datarecord[this.node.attrs.filename] || this.upload_file_name; //change to get file name
            //do not show very long name.
            // var ext = filename.substr((~-filename.lastIndexOf(".") >>> 0) + 2);
            // filename = filename.substr(0,5) + '...';
            if (this.get("effective_readonly")) {
                this.do_toggle(!!this.get('value'));
                if (this.get('value')) {
                    this.$el.empty().append($("<span/>").addClass('fa fa-download'));
                    if (filename) {
                        this.$el.append(" " + filename);
                    }
                }
            } else {
                if (this.get('value')) {
                    this.$el.children().removeClass('o_hidden');
                    this.$('.o_select_file_button').first().addClass('o_hidden');
                    this.$input.val(filename || this.get('value'));
                } else {
                    this.$el.children().addClass('o_hidden');
                    this.$('.o_select_file_button').first().removeClass('o_hidden');
                }
            }
        },
        on_clear: function () {
            this._super();
            try {
                this.$('form.o_form_binary_form').get(0).reset();
            } catch (_error) {

            }
        },
        set_value: function (value_) {
            var changed = value_ !== this.get_value();
            this._super.apply(this, arguments);
            // By default, on binary images read, the server returns the binary size
            // This is possible that two images have the exact same size
            // Therefore we trigger the change in case the image value hasn't changed
            // So the image is re-rendered correctly
            if (!changed) {
                this.trigger("change:value", this, {
                    oldValue: value_,
                    newValue: value_
                });
            }
        },
        on_save_as: function (ev) {
            var value = this.get('value');
            if (!value) {
                this.do_warn(_t("Save As..."), _t("The field is empty, there's nothing to save !"));
                ev.stopPropagation();
            } else {
                framework.blockUI();
                var c = crash_manager;
                var filename_fieldname = this.node.attrs.filename;
                var filename_field = this.view.fields && this.view.fields[filename_fieldname];
                this.session.get_file({
                    'url': '/web/content',
                    'data': {
                        'model': this.view.dataset.model,
                        'id': this.view.datarecord.id,
                        'field': this.name,
                        'filename_field': filename_fieldname,
                        'filename': filename_field ? filename_field.get('value') : this.upload_file_name || null, //change to get file name
                        'download': true,
                        'data': utils.is_bin_size(value) ? null : value,
                    },
                    'complete': framework.unblockUI,
                    'error': c.rpc_error.bind(c)
                });
                ev.stopPropagation();
            }
        },
    });

});