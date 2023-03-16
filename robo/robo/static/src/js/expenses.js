robo.define('robo.expenses', function (require) {
    "use strict";

    var core = require('web.core');
    var crash_manager = require('web.crash_manager');
    var common = require('web.form_common');
    var framework = require('web.framework');
    var data = require('web.data');
    var Model = require('web.Model');
    var utils = require('web.utils');

    var QWeb = core.qweb;
    var _t = core._t;
    var FieldBinaryFile = core.form_widget_registry.get('binary');

    var DragDropMixin = {
        init: function () {
            this._super.apply(this, arguments);
            this.listeners = [];
        },
        _isValidFile: function (file, acceptedFiles) {
            var baseMimeType, mimeType, validType, _i, _len;
            if (!acceptedFiles) {
                return true;
            }
            acceptedFiles = acceptedFiles.split(",");
            mimeType = file.type;
            baseMimeType = mimeType.replace(/\/.*$/, "");
            for (_i = 0, _len = acceptedFiles.length; _i < _len; _i++) {
                validType = acceptedFiles[_i];
                validType = validType.trim();
                if (validType.charAt(0) === ".") {
                    if (file.name.toLowerCase().indexOf(validType.toLowerCase(), file.name.length - validType.length) !== -1) {
                        return true;
                    }
                } else if (/\/\*$/.test(validType)) {
                    if (baseMimeType === validType.replace(/\/.*$/, "")) {
                        return true;
                    }
                } else {
                    if (mimeType === validType) {
                        return true;
                    }
                }
            }
            return false;
        },
        _setupEventListeners: function () {
            var elementListeners, event, listener, _i, _len, _ref, _results;
            _ref = this.listeners;
            _results = [];
            for (_i = 0, _len = _ref.length; _i < _len; _i++) {
                elementListeners = _ref[_i];
                _results.push((function () {
                    var _ref1, _results1;
                    _ref1 = elementListeners.events;
                    _results1 = [];
                    for (event in _ref1) {
                        listener = _ref1[event];
                        _results1.push(elementListeners.element.addEventListener(event, listener, false));
                    }
                    return _results1;
                })());
            }
            return _results;
        },
        _removeEventListeners: function () {
            var elementListeners, event, listener, _i, _len, _ref, _results;
            _ref = this.listeners;
            _results = [];
            for (_i = 0, _len = _ref.length; _i < _len; _i++) {
                elementListeners = _ref[_i];
                _results.push((function () {
                    var _ref1, _results1;
                    _ref1 = elementListeners.events;
                    _results1 = [];
                    for (event in _ref1) {
                        listener = _ref1[event];
                        _results1.push(elementListeners.element.removeEventListener(event, listener, false));
                    }
                    return _results1;
                })());
            }
            return _results;
        },
        destroy: function () {
            this._removeEventListeners();
            this._super.apply(this, arguments);

        },
        _define_listeners: function(drop_zone){
            var noPropagation = function (e) {
                e.stopPropagation();
                if (e.preventDefault) {
                    return e.preventDefault();
                } else {
                    return e.returnValue = false;
                }
            };
            this.listeners = [
                {
                    element: drop_zone,
                    events: {
                        "dragenter": (function (_this) {
                            return function (e) {
                                noPropagation(e);
                                _this.$('.dragDropinnerbox').toggleClass('drag-hover', true);
                            };
                        })(this),
                        "dragover": (function (_this) {
                            return function (e) {
                                var efct;
                                try {
                                    efct = e.dataTransfer.effectAllowed;
                                } catch (_error) {
                                }
                                e.dataTransfer.dropEffect = 'move' === efct || 'linkMove' === efct ? 'move' : 'copy';
                                noPropagation(e);
                                _this.$('.dragDropinnerbox').toggleClass('drag-hover', true);
                            };
                        })(this),
                        "dragleave": (function (_this) {
                            return function (e) {
                                _this.$('.dragDropinnerbox').toggleClass('drag-hover', false);
                            };
                        })(this),
                        "drop": (function (_this) {
                            return function (e) {
                                noPropagation(e);
                                return _this._drop(e);
                            };
                        })(this),
                        "dragend": (function (_this) {
                            return function (e) {
                                _this.$('.dragDropinnerbox').toggleClass('drag-hover', false);
                            };
                        })(this)
                    }
                }
            ];
        },
        _drop: function(e){

        },
    };

    var FieldDragDrop = FieldBinaryFile.extend(DragDropMixin, {
        template: 'DragDropXML',

        _drop: function (e) {
            var self = this;

            var acceptedFiles = 'application/pdf,image/*';
            if (!e.dataTransfer) {
                return;
            }
            self.$('.dragDropinnerbox').toggleClass('drag-hover', false);
            var file_node = e.dataTransfer;
            if ((this.useFileAPI && file_node.files.length)) {
                if (this.useFileAPI) {
                    var file = file_node.files[0];
                    if (file.size > this.max_upload_size) {
                        var msg = _t("The selected file exceed the maximum file size of %s.");
                        this.do_warn(_t("File upload"), _.str.sprintf(msg, utils.human_size(this.max_upload_size)));
                        return false;
                    }
                    if (file_node.files.length > 1) {
                        this.do_warn(_t("File upload"), _t("Please select only one file"));
                        return false;
                    }
                    if (self._isValidFile(file, acceptedFiles)) {
                        var filereader = new FileReader();
                        filereader.readAsDataURL(file);
                        filereader.onloadend = function (upload) {
                            var data = upload.target.result;
                            data = data.split(',')[1];
                            self.on_file_uploaded(file.size, file.name, file.type, data);
                        };
                    }
                    else {
                        var msg = _t("The selected file is not image or pdf.");
                        this.do_warn(_t("File upload"), _.str.sprintf(msg));
                        return false;
                    }
                }
                this.$('.o_form_binary_progress').show();
                this.$('button').hide();
            }
        },
        _attach_dragDrop: function () {
            var self = this;
            var drop_zone = this.view.$el[0];
            if (!drop_zone) return;

            this._define_listeners(drop_zone);

            // this._setupEventListeners();
            if (!this.get("effective_readonly")) {
                this._removeEventListeners();
                this._setupEventListeners();
            }
            this.on("change:effective_readonly", this, (function (_this) {
                return function () {
                    if (!_this.get("effective_readonly")) {
                        _this._removeEventListeners();
                        _this._setupEventListeners();
                    }
                    else {
                        _this._removeEventListeners();
                    }
                };
            })(this));
        },

        start: function () {
            var self = this;
            this._super.apply(this, arguments);
            this.view.on('attached', this, this._attach_dragDrop);
        },
        render_value: function () {
            var filename = this.upload_file_name;
            var filemime = this.upload_file_mime;

            if (filename && filename.length > 15){
                filename = filename.substring(0,15)+'...';
            }

            this.$el.children().addClass('o_hidden');
            this.$('.dragDropClass').first().toggleClass('o_hidden', false);
            this.$('.file-name').remove();
            this.$('.file-mime').remove();

            if (this.get("effective_readonly")) {
                this.do_toggle(!!this.get('value'));
                if (this.get('value')) {
                    this.$('.dragDropinnerbox').append(QWeb.render('filemime', {widget: this, mime: filemime}));
                    this.$('.dragDropinnerbox').append('<span class="file-name">' + filename + '</span>');
                    this.$('.dragDropText').toggleClass('o_hidden', true);
                    this.$('.dragDropinnerbox .o_clear_file_button').toggleClass('o_hidden', false);
                }
            } else {
                if (this.get('value')) {
                    this.$('.dragDropinnerbox').append(QWeb.render('filemime', {widget: this, mime: filemime}));
                    this.$('.dragDropinnerbox').append('<span class="file-name">' + filename + '</span>');
                    this.$('.dragDropText').toggleClass('o_hidden', true);
                    this.$('.dragDropinnerbox .o_clear_file_button').toggleClass('o_hidden', false);
                } else {
                    this.$('.dragDropTextIcon').toggleClass('o_hidden', true);
                    this.$('.dragDropText').toggleClass('o_hidden', false);
                    this.$('.dragDropinnerbox .o_clear_file_button').toggleClass('o_hidden', true);
                }
            }
        },
    });

    core.form_widget_registry.add('dragDrop', FieldDragDrop);
    return {
        DragDropMixin: DragDropMixin,
    }
});