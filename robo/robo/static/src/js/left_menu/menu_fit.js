 robo.define('robo.roboMenuFit', function(require) {
     'use strict';

     var core = require('web.core');
     var localStorage = require('web.local_storage');
     var Widget = require('web.Widget');



     var RoboMenuFit = Widget.extend({

         init: function(){
             this._super.apply(this, arguments);
             this.$o_main = this.getParent().getParent().$el.find('.o_main');
             if (localStorage.getItem('robo_menu_expanded')){
                 this.$o_main.toggleClass('robo-menu-fit', true);
             }

         },
         fireResize: function(){
             core.bus.trigger('resize');
             if (window.dispatchEvent) {
                 window.dispatchEvent(new Event('resize'));
             }
         },
         start: function(){
           var self = this;

           this.$el.on('click', '.icon-backward-circle.robo-menu-icon.robo-menu-fit-icon', function(){
             localStorage.setItem('robo_menu_expanded', 1);
             self.$o_main.toggleClass('robo-menu-fit', true);
             self.fireResize();
           });
           this.$el.on('click', '.icon-forward-circle.robo-menu-icon.robo-menu-fit-icon', function(){
             localStorage.removeItem('robo_menu_expanded');
             self.$o_main.toggleClass('robo-menu-fit', false);
             self.fireResize();
           });

           return this._super.apply(this, arguments);
         },

     });

     return RoboMenuFit;

 });
