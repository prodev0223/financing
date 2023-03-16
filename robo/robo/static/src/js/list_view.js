robo.define('robo.ListView', function (require) {
"use strict";

var list_view = require('web.ListView');
var core = require('web.core');
var data = require('web.data');
var data_manager = require('web.data_manager');
var DataExport = require('web.DataExport');
var formats = require('web.formats');
var common = require('web.list_common');
var Model = require('web.DataModel');
var Pager = require('web.Pager');
var pyeval = require('web.pyeval');
var session = require('web.session');
var Sidebar = require('web.Sidebar');
var utils = require('web.utils');
var View = require('web.View');
require('web_editor.backend');

var list_widget_registry = core.list_widget_registry;


var Column = core.list_widget_registry.get('field');
var ColumnQuantityLarge = Column.extend({
    format: function (row_data, options) {
        var value = formats.format_value(row_data[this.id].value || 0, 'none', 0);
// Might need to convert if string in the form is written with a comma;
//        if (typeof value === 'string') {
//            value = parseFloat(value.replace(",","."));
//        }
//        console.log(typeof value);
        value = this.human_number(value, 3);
        return value;
    },
    human_number: function (number, decimals){
        var is_number_negative = ((number < 0.0) ? true : false);
        number = Math.abs(number);
        var prefix = '';
        var decimals = decimals | 0;
        var d2 = Math.pow(10, decimals);
        var val = "MGTPE";
        var i = val.length-1, s;
        while( i ) {
            s = Math.pow(10,i--*3+3);
            if( s <= number ) {
                number = Math.round(number*d2/s)/d2;
                prefix = val[i];
            }
        }
        number = number.toFixed(3);
        if (is_number_negative) {
            number = '-' + number;
        }
        return number + prefix;
    },
});


list_widget_registry
    .add('field.quantity_large', ColumnQuantityLarge)
});
