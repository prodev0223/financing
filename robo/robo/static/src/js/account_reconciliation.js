robo.define('robo.reconciliation', function (require) {
    "use strict";

    var reconciliation = require('account.reconciliation');

    reconciliation.manualReconciliation.include({
      events: _.defaults({
        "keyup input.filter_name": "filterNameHandler",
        "click .show_more": "showMoreButtonClickHandler",
      },  reconciliation.manualReconciliation.prototype.events),

      init: function(parent, context){//override
        this._super.apply(this, arguments);
        this.name_filter='';
        this.filter_timeout;
        this.lock_filter = false;
      },
      getFiltered: function(data){
        var collection = _.clone(data), self = this;
        if (!self.name_filter) return data;
        collection =  _.extend(
            collection,
            {
              items: _.filter(data.items, function(el){
                if (!el.partner_name) return false;
                if (el.partner_name.toUpperCase().indexOf(self.name_filter.toUpperCase()) != -1) return true;
                    else return false;
              }),
            }
        );
        return collection;
      },
      getDisplayedCollections: function() {//override
        var collections = [];
        if (this.mode === 'customers' || this.mode === 'all') { collections.push(this.getFiltered(this.customers_data))}
        if (this.mode === 'suppliers' || this.mode === 'all') { collections.push(this.getFiltered(this.suppliers_data)) }
        if (this.mode === 'others' || this.mode === 'all') { collections.push(this.getFiltered(this.accounts_data)) }
        return collections;
     },
     filterNameHandler: _.debounce(function(e){
       var self = this;
       if (e) {
        self.name_filter = $(e.currentTarget).val();
       }
       if (self.lock_filter) {
            clearTimeout(self.filter_timeout);
            self.filter_timeout = setTimeout(self.filterNameHandler.bind(self),1000);
            return;
        }
       self.$(".reconciliation_lines_container").css("opacity", 0);
        _.each(self.getChildren(), function(child) {
                child.data.displayed = false;
                child.destroy();
        });
        self.lock_filter = true;
        return $.when(self.updateProgress(false))
        .then(function(){
            var children_promises = [];
            self.$(".reconciliation_lines_container").animate({opacity: 1}, self.aestetic_animation_speed);
            _.each(self.getChildren(), function(child) {
                children_promises.push(child.finishedLoadingMoveLines);
            });
            return $.when.apply($, children_promises);
        }).always(function(){self.lock_filter = false;});
     }, 300),
     updateProgress: function(animate_entrance){//override
        var self = this;
        return $.when(this._super.apply(this,[animate_entrance]))
        .then(function(){
            self.updateShowMoreButton();
        });
     },
     showMoreButtonClickHandler: function(){
        var self = this;
        self.num_reconciliations_fetched_in_batch += 10;
        self.filterNameHandler.call(self);
     },
     updateShowMoreButton: function() {
        var nbr_to_display=0, items_remaining=0;
        this.getDisplayedCollections().forEach( function(element, index) {
            nbr_to_display += element.items.length;
        });
        items_remaining = nbr_to_display - this.getChildren().length;
        if (items_remaining > 0){
            this.$el.find(".show_more").show().find(".num_items_remaining").text(items_remaining);
        }
        else
            this.$el.find(".show_more").hide();
     },
    });



});