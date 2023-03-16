robo.define('pivot_freeze.pivot', function (require) {
    "use strict";

    var Pivot = require('web.PivotView');
    var config = require('web.config');

    Pivot.include({
        init: function(){
          this._super.apply(this, arguments);
          this.measures_ids = {};
          this.order_rule = undefined;

          if (this.fields_view  &&  this.fields_view.arch && this.fields_view.arch.attrs) {
              this.order_measure = this.fields_view.arch.attrs.order;
              if (this.fields_view.arch.attrs.order_rule === 'asc') {
                  this.order_rule = true;
              }
          }
        },
        display_table: function () {
            this._super();

            //ROBO: if mobile phone size return immediately without freeze panes
            if (config.device.size_class <= config.device.SIZES.XS) {
                return;
            }

            //freeze header and one left column
            this.$('table').tableHeadFixer({'z-index' : 50, left: 1});
            this.$('table').css({'border-collapse': 'separate'});

            //for robo 9: push scrollbar event to the parent of the table
            this.$el.css({'height': '100%'});
            this.$('table').parent().css({'height': '100%'});

            //remove transition from table in robo 9 with material backend theme 9 -- look pivot_view.less
        },
        do_show: function(){
          var self = this;
          return $.when(this._super.apply(this, arguments)).then(function(){
              if (self.order_measure !== undefined && self.measures_ids[self.order_measure] !== undefined && self.measures[self.order_measure] !== undefined){
                self.sort_rows(self.measures_ids[self.order_measure], self.order_measure, self.order_rule);
                self.display_table();
              }
          });
        },
        draw_headers: function($thead, headers){
          this._super.apply(this, arguments);

          var i, j, cell;
          for (i = 0; i < headers.length; i++) {
            for (j = 0; j < headers[i].length; j++) {
                cell = headers[i][j];
                if (cell && cell.measure && cell.id){
                  this.measures_ids[cell.measure] = cell.id;
                }
            }
          }
        }
    });

});