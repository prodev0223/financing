robo.define('percentage_widget', function (require) {
    "use strict";

    //TODO: remove trash?
    // var core = require('web.core');
    // var FieldFloat = core.form_widget_registry.get('float');
    // var Column = core.list_widget_registry.get('field');
    //
    // // Form View
    // var PercentageWidget = FieldFloat.extend({
    //     template: 'PercentageWidget',
    //     render_value: function () {
    //         if (!this.get("effective_readonly")) {
    //             this._super();
    //         } else {
    //             var _value = parseFloat(this.get('value'));
    //             if (isNaN(_value)) {
    //                 this.$el.find(".percentage_filed").text('');
    //             } else {
    //                 this.$el.find(".percentage_filed").text(
    //                     (_value * 100).toFixed(2) + ' %');
    //             }
    //         }
    //     }
    // });
    // core.form_widget_registry.add('percentage', PercentageWidget);
    //
    // // List View
    // var ColumnPercentage = Column.extend({
    //     _format: function (row_data, options) {
    //         var _value = parseFloat(row_data[this.id].value);
    //         if (isNaN(_value)) {
    //             return null;
    //         }
    //         return (_value * 100).toFixed(2) + ' %';
    //     }
    // });
    // core.list_widget_registry.add('field.percentage', ColumnPercentage)
});