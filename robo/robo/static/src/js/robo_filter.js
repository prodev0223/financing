robo.define('robo.SearchExtend', function (require) {
    "use strict";

    var filter_menu = require('web.FilterMenu');
    var groupby_menu = require('web.GroupByMenu');

    filter_menu.include({
      init: function(parent, filters){
        this._super.apply(this, arguments);
        this.search_add_custom = true;
        if (parent.ViewManager && parent.ViewManager.action && parent.ViewManager.action.context && parent.ViewManager.action.context.search_add_custom !== undefined){
          this.search_add_custom = parent.ViewManager.action.context.search_add_custom;
        }
      }
    });


    groupby_menu.include({
      init: function(parent, groups){
        this._super.apply(this, arguments);
        this.search_add_custom = true;
        if (parent.ViewManager && parent.ViewManager.action && parent.ViewManager.action.context && parent.ViewManager.action.context.search_add_custom !== undefined){
          this.search_add_custom = parent.ViewManager.action.context.search_add_custom;
        }
      }
    });

});