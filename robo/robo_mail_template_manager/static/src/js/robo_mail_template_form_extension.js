//robo.define('robo_mail_template_manager.FormRenderingEngine', function (require) {
//    "use strict";
//
//    var config = require('web.config');
//    var core = require('web.core');
//    var FormRenderingEngine = require('web.FormRenderingEngine');
//
//    FormRenderingEngine.include({
//        init: function(view, options){
//            this._super(view);
//
//        },
//        do_show: function($tag) {
//            var self = this;
//            return $.when(this._super.apply(this, arguments)).then(function(){
//                if (self.$el.find('.robo-mail-compose-body').length > 0) {
//                    var the_modal = $(self.getParent().getParent().$modal).find('.modal-dialog')
//                    if (the_modal.length > 0) {
//                        the_modal.toggleClass('robo-wizard-wide', true);
//                    }
//                }
//            });
//        },
//    });
//
//});
//
//
//robo.define('robo_mail_template_manager.ControlPanel', function (require) {
//    "use strict";
//
//    var config = require('web.config');
//    var ControlPanel = require('web.ControlPanel');
//    var core = require('web.core');
//    var session = require('web.session');
//
//    ControlPanel.include({
//        _render_breadcrumbs: function (breadcrumbs) {
//            var self = this;
//            return $.when(this._super(breadcrumbs)).then(function () {
//                console.log('Works')
//            })
//        }
//    });
//});
//
//
//
//
//
//
//
