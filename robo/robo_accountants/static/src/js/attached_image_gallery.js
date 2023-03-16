robo.define('robo.attachment_image_gallery', function (require) {
"use strict";

    var core = require('web.core');
    var Model = require('web.DataModel');
    var FormRelational = require('web.form_relational');
    var h = require('snabbdom.h');
    var patch = require('snabbdom.patch');

    var AttachmentImageGallery = FormRelational.AbstractManyField.extend({
        className: "o_form_field_attachment_image_gallery",
        tag_template: "FieldMany2ManyAttachmentImagegallery",
        events: {},
        init: function (parent, data) {
            this._super.apply(this, arguments);
            this.attachment_data = [];
            this.AttachmentModel = new Model('ir.attachment');
            this.view.on("load_record", this, this._fetch);
            this.dataset.on('dataset_changed', this, this._fetch);
        },
        start: function () {
            var self = this;
            this.innerDiv = document.createElement('div');
            this.el.appendChild(this.innerDiv);
        },
        _fetch: function() {
            var self = this;
            this.AttachmentModel.query(['local_url', 'display_name', 'id'])
                .filter([['id', 'in', this.dataset.ids], ['index_content', '=', 'image']])
                .all().then(function (attachments) {
                    self.attachment_data = attachments;
                    self._render();
                });
        },
        _render: function() {
            var self = this;
            var vnode = h('div', [].concat(
                                 _(self.attachment_data).map(function (attachment) {
                                    var img_node = h('a',
                                                    {attrs: {
                                                        'href': attachment.local_url,
                                                        'target': '_blank'
                                                        }
                                                    },
                                                    [h('img',
                                                     {attrs: {
                                                        'src': attachment.local_url,
                                                        'style': 'width: 100%;',
                                                        'title': attachment.display_name
                                                        }
                                                     })
                                                    ])
                                    return img_node;
                                 })
                             ));
            this.innerDiv = patch(this.innerDiv, vnode);
        }
    });
    core.form_widget_registry.add('attachment_image_gallery', AttachmentImageGallery);
});