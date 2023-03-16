robo.define('l10n_llt_paroll.popup', function (require) {
"use strict";

var core = require('web.core');
var form_common = require('web.form_common');
var formats = require('web.formats');
var Model = require('web.Model');

var QWeb = core.qweb;

var PopupWidget = form_common.AbstractField.extend({
    render_value: function() {
        var self = this;
        var info = JSON.parse(this.get('value'));
        if (info !== false) {
            var text = '';
            if (info.text){
                var text = info.text;
            }
            this.$el.html('<div role="button" class="js_popup fa fa-info-circle" style="color: red;"></div>');
            var options = {
                content: QWeb.render('PopOverInfo', {
                        'text': text,
                        }),
                html: true,
                placement: 'bottom',
                title: 'Info',
            };
            _.each(this.$('.js_popup'), function(k, v){
                $(k).popover(options);
            })
        }
        else {
            this.$el.html('');
        }
    },
});

core.form_widget_registry.add('popup', PopupWidget);

});