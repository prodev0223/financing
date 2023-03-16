robo.define('robo.utils', function (require) {
    "use strict";

    var Class = require('web.Class');
    var formats = require('web.formats');
    var session = require('web.session');
    var utils = require('web.utils');
    var translation = require('web.translation');

    var _t = translation._t;

    //@decimals nbr of precision in formatted number with letter; numbers < 1000 formatted with manual precision
    var human_value = function(number,decimals){
        return format_LT_value(number, decimals);
    };


    var kas_to_sauksm = function(zodis){

            if (!String.prototype.endsWith) {
                  String.prototype.endsWith = function(searchString, position) {
                      var subjectString = this.toString();
                      if (typeof position !== 'number' || !isFinite(position)
                          || Math.floor(position) !== position || position > subjectString.length) {
                        position = subjectString.length;
                      }
                      position -= searchString.length;
                      var lastIndex = subjectString.indexOf(searchString, position);
                      return lastIndex !== -1 && lastIndex === position;
                  };
}

            var galunes = [['as', 'ai'], ['ė', 'e'], ['is', 'i'], ['us', 'au'], ['ys', 'y']];

            for (var i = 0; i < galunes.length; i++) {
                if (zodis.endsWith(galunes[i][0])) {
                    return zodis.substr(0, zodis.length - galunes[i][0].length) + galunes[i][1];
                }
            }
            return zodis;
    };

    var format_LT_value = function(number, decimals){
        if (typeof number != 'number') return number ? number : '';

        var decimal_point = _t.database.parameters.decimal_point;
        var nbrOfDigits = Math.abs(number).toFixed().length;
        var val = _t(" kMGTPE");
        decimals = Math.min(decimals | 0, 2);

        if (nbrOfDigits <= 3){
            var precision = "0222"[nbrOfDigits];
            //remove trailing zeros
            return (+number.toFixed(precision)).toString().replace('.', decimal_point);
        }
        else{
            var index = ~~(nbrOfDigits/3);
            var indexOfLetter =  (nbrOfDigits%3 ? index : index-1);
            var s = Math.pow(10,indexOfLetter*3);
            var d2 = Math.pow(10, decimals);
            number = Math.round(number*d2/s)/d2;
            //remove trailing zeros
            return (+number.toFixed(decimals)).toString().replace('.', decimal_point) + val[indexOfLetter];
        }

    };

    var kas_to_kam = function(zodis){
        var galunes = [["as", "ui"], ["a", "ai"], ["ė", "ei"], /*["e", "ei"],*/
                ["tis", "čiui"], ["dys", "džiui"],["tys","čiui"], ["dis","džiui"],["is", "iui"],
                ["ys", "iui"], ["us", "ui"]];

        if (!String.prototype.endsWith) {
              String.prototype.endsWith = function(searchString, position) {
                  var subjectString = this.toString();
                  if (typeof position !== 'number' || !isFinite(position)
                      || Math.floor(position) !== position || position > subjectString.length) {
                    position = subjectString.length;
                  }
                  position -= searchString.length;
                  var lastIndex = subjectString.indexOf(searchString, position);
                  return lastIndex !== -1 && lastIndex === position;
              };
            }

        for (var i = 0; i < galunes.length; i++) {
            if (zodis.endsWith(galunes[i][0])) {
                return zodis.substr(0, zodis.length - galunes[i][0].length) + galunes[i][1];
            }
        }
        return zodis;
    };

     var render_monetary = function(value, currency_id) {
        var currency = session.get_currency(currency_id);
        var digits_precision = currency && currency.digits;
        value = formats.format_value(value || 0, {type: "float", digits: digits_precision});
        if (currency) {
            if (currency.position === "after") {
                value += currency.symbol;
            } else {
                value = currency.symbol + value;
            }
        }
        return value;
     };

     //if for example we have event A and before finish we add B, and later before finish we add C, we want to start
    // success callback only once and only after A,B,C are finished

    var MutexDropPrevious = Class.extend({
        init: function () {
            // this.def = $.Deferred().resolve();
            this.defs = [];
        },
        add: function (deferred) {
            if (this.current_def) { this.current_def.reject();}
            var res = $.Deferred();
            this.defs.push(deferred);
            $.when.apply($, this.defs).then(res.resolve, res.reject);
            this.current_def = res;
            return res.promise();
        }
    });

    return {
        human_value: human_value,
        format_LT_value: format_LT_value,
        kas_to_kam: kas_to_kam,
        kas_to_sauksm: kas_to_sauksm,
        render_monetary: render_monetary,
        MutexDropPrevious: MutexDropPrevious,
    };

});


robo.define('robo_tags', function (require) {
    "use strict";

    var core = require('web.core');
    var list_widget_registry = core.list_widget_registry;
    var Column = list_widget_registry.get('field');

    // List View
    var ColumnRoboTags = Column.extend({
        _format: function(row_data, options) {
            var value = row_data[this.name]['value'];
            if (!value){
                value = '';
            }
            return value;
        },
    });
    list_widget_registry.add('field.roboTags', ColumnRoboTags);
});