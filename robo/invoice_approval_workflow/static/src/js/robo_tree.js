robo.define('invoice_approval.RoboTree', function (require) {
    "use strict";

    var core = require('web.core');

    var _t = core._t;
    var list_widget_registry = core.list_widget_registry;
    var ColumnState = list_widget_registry.get('field.roboStatus');

    ColumnState.include({
        // Overrides the default robo tree column state. Only change to the default is that this sets the state field
        // to be shown in full rather than splitting the state by space and only using the first word of it.
        _format: function(row_data){
            var state = row_data[this._state_field] && row_data[this._state_field].value;
            if (state !== 'in_approval') {
                return this._super.apply(this, arguments);
            } else {
                var selection = (
                                    this['multi-col'] &&
                                    this['multi-col'][this._state_field] &&
                                    this['multi-col'][this._state_field].selection
                                ) ||
                                this.selection
                if(!_.isEmpty(state) && !_.isEmpty(selection)){
                        var selection_value = _(selection).detect(function(choice){
                            return choice[0] === state;
                        });
                        if (!_.isUndefined(selection_value) && !_.isUndefined(selection_value[1])) {
                            var curr_status_template = this._my_template(state, selection_value[1]);
                            return curr_status_template;
                        }
                        else{
                            return;
                        }
                }
                else{
                    return;
                }
            }
        },
    });

});