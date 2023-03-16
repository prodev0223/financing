robo.define('robo.Sidebar', function (require) {
    "use strict";

    var config = require('web.config');
    var core = require('web.core');
    var Sidebar = require('web.Sidebar');

    var QWeb = core.qweb;

    Sidebar.include({
        init: function(parent, options){
          this._super(parent, options);
          if (options && options.robo_front){
              this.robo_front = true;
          }
        },
        // start: function(){
        //    var self = this;
        //    this._super.apply(this, arguments);
        //    // Sidebar.prototype.start();
        //    this.$el.on('click', '.sidebar-mobile a', function(event) {
        //        var section = $(this).data('section');
        //        var index = $(this).data('index');
        //        var item = self.items[section][index];
        //        if (item.callback) {
        //            item.callback.apply(self, [item]);
        //        }
        //        event.preventDefault();f
        //    });
        // },
        redraw: function() {
            // if (config.device.size_class <= config.device.SIZES.XS){
            //     this.$el.html(QWeb.render('Sidebar_mobile', {widget: this}));
            // }
            if (this.robo_front){
                this.$el.html(QWeb.render('Sidebar.roboFront', {widget: this}));
            }
            else{
                // Sidebar.prototype.redraw();
                this._super.apply(this, arguments);
            }
        }
    });

});