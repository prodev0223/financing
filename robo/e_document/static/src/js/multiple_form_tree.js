robo.define('robo.MultipleFormTree', function (require) {
    "use strict";


    var core = require('web.core');
    var list_widget_registry = core.list_widget_registry;
    var Column = list_widget_registry.get('field');
    var RoboTree = require('robo.RoboTree');
    var state_colors = {draft: 'draftClass',
                        open: 'openClass',
                        confirm: 'openClass',
                        paid: 'paidClass',
                        done: 'paidClass',
                        e_signed: 'paidClass',
                        cancel: 'cancelClass'
    };
    var MultipleFormTree = RoboTree.extend({

        init: function() {
            this._super.apply(this, arguments);
        },

        do_activate_record: function (index, id, dataset, view) {


            this.dataset.ids = dataset.ids;
            if (this.records.get(id).hasOwnProperty('attributes')) {
                var view_id = this.records.get(id).attributes.view_id[0];
                this.dataset.index = index;
                var additional_context = {
                    pager_actions: {
                    'element_views': _.object(this.dataset.ids, _.map(dataset.ids, function (id) {
                                return this.records.get(id).attributes.view_id[0];
                            }, this) , this),
                }
                };

                this.dataset.context = _.extend({}, this.dataset.context, additional_context);
                this.trigger('switch_mode_with_id', 'form', {pager: true}, view_id);
            }
        },
    });

    core.view_registry.add('multiple_form_tree', MultipleFormTree);

    var ColumnStateWithIcon = list_widget_registry.get('field.roboStateIcon');
    var ColumnDocumentStatus = ColumnStateWithIcon.extend({
        _state_colors: state_colors,
        _value_icon_class: {true: 'icon-cross-circle cancelClass reject-document-icon'},
        _value_icon_title: {true: 'Atmesta'},
        _value_icon_field: 'rejected',
    });

    var AgreedWithDocumentState = Column.extend({
        _format: function(row_data){
            var _state_field = 'employee_agrees_with_document'
            var value = row_data[_state_field] && row_data[_state_field].value;
            if(!_.isEmpty(value)){
                return value;
            } else {
                return '';
            }
        },
    });
    list_widget_registry.add('field.documentStatus', ColumnDocumentStatus);
    list_widget_registry.add('field.AgreedWithDocumentState', AgreedWithDocumentState);
});

