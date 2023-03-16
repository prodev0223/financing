 robo.define('robo.roboMenuHelp', function(require) {
     'use strict';

     var Model = require('web.DataModel');
     var Session  = require('web.session');
     var Widget = require('web.Widget');


     var RoboHelp = Widget.extend({
         template: 'RoboHelpLine',
         init: function(){
             this._super.apply(this, arguments);
             this.model = new Model('res.company');

             this.mobile = '';
             this.email = '';
             this.logo = '';
             this.name = '';
         },
         willStart: function(){
            var that = this;
            return this.model.call("robo_help",[Session.company_id]).done(function(result) {
                        that.mobile = result.mobile;
                        that.email = result.email;
                        that.logo = result.logo;
                        that.name = result.name;
                    });

         },
         start: function(){

           var that = this;

           this.$el.on('click', '.robo-help-question', function(){
               that.do_action('e_document.robo_issue_action',{clear_breadcrumbs: true});
           });
           this.$el.on('click', '.robo-mail', function(){
             that.$('.robo-mobile-info-detail').text(that.email);
           });
           this.$el.on('click', '.robo-mobile', function(){
             that.$('.robo-mobile-info-detail').text(that.name + ': ' + that.mobile);
           });
         },

     });

     return RoboHelp;

 });
