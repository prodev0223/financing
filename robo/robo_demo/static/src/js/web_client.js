robo.define('robo_demo.web_client', function (require) {
    "use strict";

    var ActionManager = require('web.ActionManager')
    var config = require('web.config');
    var core = require('web.core');
    var Model = require('web.DataModel');
    var session = require('web.session');
    var WebClient = require('web.WebClient');

    var QWeb = core.qweb;


    WebClient.include({

        bind_events: function(){
          var self = this;
          this._super.apply(this, arguments);

          core.bus.on('make_blur',null, function(action){
              self.$('.o_main_content .info_block').remove();
              self.$('.o_main_content').css('position', 'relative');
              self.$('.o_main_content .o_control_panel').toggleClass('blur_menu', false);
              self.$('.o_main_content .o_content').toggleClass('blur_menu', false);
               if (action && action.type === 'ir.actions.client' && action.xml_id && action.xml_id.startsWith && action.xml_id.startsWith('robo_demo.make_blur')){
                self.$('.o_main_content .o_control_panel').toggleClass('blur_menu', true);
                self.$('.o_main_content .o_content').toggleClass('blur_menu', true);
                self.$('.o_main_content').removeAttr('position');
                self.$('.o_main_content').append(QWeb.render('make_blur.message', {params: action.params}));
            }
          });
        },

    });

    ActionManager.include({
        do_action: function(action, options){
            var self = this;
            core.bus.trigger('make_blur', action);
            if (action && action.type === 'ir.actions.client' && action.xml_id && action.xml_id.startsWith && action.xml_id.startsWith('robo_demo.make_blur')){
                action = { type: 'ir.actions.act_window_close' };
                // return $.Deferred().reject();
            }

            return this._super.apply(this, [action, options]);
        }
    });


});


