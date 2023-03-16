robo.define('robo_theme_v10.ListView', function (require) {
"use.strict";

    var ListView = require('web.ListView');

    ListView.include({
        /* To turn off uncheck process lag in thead during column sort.
        * */
        sort_by_column: function(){
             this.$('thead .o_list_record_selector input').prop('checked', false);
             return this._super.apply(this, arguments);
        },
    });



});

