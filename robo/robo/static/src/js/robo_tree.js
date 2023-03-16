robo.define('robo.RoboTree', function (require) {
    "use strict";

    var ActionManager = require('web.ActionManager');
    var core = require('web.core');
    var data = require('web.data');
    var data_manager = require('web.data_manager');
    var Dialog = require('web.Dialog');
    var FavoriteMenu = require('web.FavoriteMenu');
    var formats = require('web.formats');
    var ListView = require('web.ListView');
    var Model = require('web.DataModel');
    var pyeval = require('web.pyeval');
    var RoboFrontActions = require('robo.roboFrontActions');
    var roboUtils = require('robo.utils');

    var search_input = require('web.search_inputs');
    var session = require('web.session');
    var Sidebar = require('web.Sidebar');
    var utils = require('web.utils');
    var ViewManager = require('web.ViewManager');

    var _t = core._t;
    var list_widget_registry = core.list_widget_registry;
    var Column = list_widget_registry.get('field');
    var QWeb = core.qweb;

    var state_colors = {
        draft: 'draftClass', proforma: 'proformaClass', proforma2: 'proforma2Class',
        open: 'openClass', paid: 'paidClass', cancel: 'cancelClass',
        //for expenses
        reported: 'openClass', done: 'paidClass', refused: 'cancelClass', imported: 'importedClass',
        //for picking
         waiting: 'openClass', confirmed: 'noticeClass', partially_available: 'importedClass',
         assigned: 'paidClass',
        //for sale.order
        sent: 'importedClass', sale: 'openClass',
        //for purchase.order
        'to approve': 'noticeClass', purchase: 'openClass',
    };

    var upload_colors = {
        sent: 'sent', accepted: 'accepted', done: 'done',
        rejected: 'rejected', need_action: 'need_action'
    };


    var ColumnExpenseType = Column.extend({
         /**
         * @private
         * @return: invoice picture with special color if advance payment repaid (normal) or not (red)
         */
        _format: function (row_data, options) {
            // var bWithCheck = !!row_data[this.id].value,
             var bCashRepaid = !! (row_data['is_cash_advance_repaid'] && row_data['is_cash_advance_repaid'].value),
                bDraft = !!(row_data['state'] && row_data['state'].value==='draft'),
                bWithExpenseId = !!(row_data['expense_move_id'] && row_data['expense_move_id'].value),
                bAdvancePayment = !!(row_data['advance_payment'] && row_data['advance_payment'].value),

                currency_id = row_data['company_currency_id'] && row_data['company_currency_id'].value && row_data['company_currency_id'].value[0],
                ap_employee_name = row_data['ap_employee_id'] && row_data['ap_employee_id'].value && row_data['ap_employee_id'].value[1];

             if (bWithExpenseId  && !bDraft && bAdvancePayment) {

                 var cash_to_repay = row_data['cash_advance_left_to_repay'] && row_data['cash_advance_left_to_repay'].value;
                 var lang;
                 try {
                    lang = options['lang'];
                 }
                 catch (err) {
                    lang = 'lt_LT';
                 }

                 //format the text to display in the title
                 cash_to_repay = (cash_to_repay ? _t(' suma: ') + roboUtils.render_monetary(Math.abs(cash_to_repay), currency_id): '') + '<br/>';
                 ap_employee_name = (ap_employee_name ? _t('Darbuotojui ') + (lang == 'lt_LT'?this._naudininkas(ap_employee_name):ap_employee_name) : _t(' darbuotojui'));

                 return _.str.sprintf('<span class="icon-papers %s" style="font-size:2em;" data-toggle="tooltip" title="%s"></span>',
                     !bCashRepaid ? 'info-expense-icon-color' : 'normal-expense-icon-color',
                     !bCashRepaid ? _t('Negrąžinta')+cash_to_repay+ap_employee_name : _t('Grąžinta ') + (ap_employee_name[0].toLowerCase()+ap_employee_name.slice(1))
                 );
             }
             else{
                 return _.str.sprintf('');
             }
        },

        _naudininkas: function(name){
            var words = name.split(' ');
            return _(words).map(function(v){
                return roboUtils.kas_to_kam(v);
            }, this).join(' ');
        },

    });

    var ColumnHtmlToText = Column.extend({
         _format: function (row_data, options) {
             var result;
             if (row_data[this.id] && row_data[this.id]){
                 try {
                     result = _.str.escapeHTML($(row_data[this.id].value).text());
                 }
                 catch(error){
                     result = _.str.escapeHTML(row_data[this.id].value);
                 }
                 return result;
             }
             return '';
         }

    });

    var ColumnState = Column.extend({
        _state_field: 'state',
        _state_colors: state_colors,
        _tag: 'span',
        _my_template: function(state_value, state_name){
            return _.template('<<%-tag%> class=<%=state_class%>><%-state%></<%-tag%>>')({
                state_class: this._state_colors[state_value],
                state: state_value && state_name,
                tag: this._tag,
            });
        },
        _format: function(row_data){
            var state = row_data[this._state_field] && row_data[this._state_field].value;
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
                        var curr_status_template = this._my_template(state, selection_value[1].split(" ")[0]);
                        return curr_status_template;
                    }
                    else{
                        return;
                    }
            }
            else{
                return;
            }
        },
    });

    var BankExportState = Column.extend({
        _format: function(row_data){
            var _state_field = 'bank_export_state_html'
            var value = row_data[_state_field] && row_data[_state_field].value;
            if(!_.isEmpty(value)){
                   return value;
            }
            else{
                _state_field = 'swed_bank_export_state_html'
                var value = row_data[_state_field] && row_data[_state_field].value;
                if(!_.isEmpty(value)){
                   return value;
                }
                else{
                    return '';
                }
            }
        },
    });

    var ColumnAddState = ColumnState.extend({
        _tag: 'div',
        _format: function(row_data){
            var template = this._super.apply(this, arguments);

            var options = pyeval.py_eval(this.options || '{}');
            //name of currency field is defined either by field attribute, in view options or we assume it is named currency_id
            var currency_field = (_.isEmpty(options) === false && options.currency_field) || this.currency_field || 'currency_id';
            var currency_id = row_data[currency_field] && row_data[currency_field].value[0];
            var currency = session.get_currency(currency_id);
            var digits_precision = this.digits || (currency && currency.digits);
            var value = formats.format_value(row_data[this.id].value || 0, {
                type: this.type,
                digits: digits_precision
            }, options.value_if_empty);

            if (currency) {
                if (currency.position === "after") {
                    value += '&nbsp;' + currency.symbol;
                } else {
                    value = currency.symbol + '&nbsp;' + value;
                }
            }
            return value + (_.isEmpty(template) ? '' : template);
        }
    });
    var ColumnInvoiceState = ColumnState.extend({
        _tag: 'div',
        _format: function(row_data){
            var data = JSON.parse(row_data[this.id]["value"]);
            var digits_precision = data.precision;
            var value = formats.format_value(data.amount || 0, {
                type: "monetary",
                digits: digits_precision
            });
            var position = data.position;
            if (position === "after") {
                value += '&nbsp;' + data.symbol;
            }
            else {
                value = data.symbol + '&nbsp;' + value;
            }
            value = value + "<div class=" + data.class + ">" + data.state + "</div>";
            return value;
        }
    });
    var ColumnAddStateExp = ColumnAddState.extend({
       _state_field: 'expense_state',
    });

    var ColumnUploadState = ColumnState.extend({
        _state_colors: upload_colors,
        _info_box: function(reason){
            return _.template('<i class="icon-bubble-alert reject-icon" data-toggle="tooltip" title="<%-title%>"/>')(
                {
                    title: _.escape(reason),
                });
        },
        _format: function (row_data, options) {
            var template = this._super.apply(this, arguments);
            var state = row_data[this._state_field] && row_data[this._state_field].value;
            if (state && state === 'rejected') {
                if (row_data['reason'] && !_.isEmpty(row_data['reason'].value)) {
                    var reason = row_data['reason'].value;
                    return template + this._info_box(reason);
                }
            }
            return template;
        },
    });
    /*
        Column in which we want to display additionaly one icon on the left
     */
    var ColumnWithIcon = ColumnState.extend({
        _value_icon_class : {}, //with icon class include color class if necessary {'value': 'icon-class'}
        _value_icon_field: '', //field which values we use in _value_icon_class
        _value_icon_title: {},
        _info_icon: function(icon_class, title){
             return _.template('<i class="<%-icon_class%>" data-toggle="tooltip" title="<%-title%>"/>')(
                {
                    icon_class: icon_class,
                    title: title?title:'',
                });
        },
        _format: function(row_data, options){
            var self = this;
            var template = this._super.apply(this, arguments);
            var field = row_data[this._value_icon_field] || row_data[self.id];
            if (row_data.hasOwnProperty('susijes_isakymas_pasirasytas')){
                var ParentSigned = row_data['susijes_isakymas_pasirasytas']['value'];
            }
            else {
                var ParentSigned = false;
            }
            //special case for boolvalue
            var field_value = field.value;
            if (_.isBoolean(field.value)){
                field_value = 'false';
                if (field.value){
                  field_value = 'true'
                }
            }

            var icon_class = _(this._value_icon_class).find(function (v, k) {
                return k == field_value
            });
             var icon_title= _(this._value_icon_title).find(function (v, k) {
                return k == field_value
            });
            if (!_.isUndefined(icon_class)) {
                return template + this._info_icon(icon_class, icon_title);
            }
            if (ParentSigned){
                icon_class = 'icon-checkmark-circle paidClass reject-document-icon'
                icon_title = 'Susijęs įsakymas pasirašytas'
                return template + this._info_icon(icon_class, icon_title);
            }

            return template
        }
    });

    var ColumnWithOtherFieldBelow = Column.extend({
        _field_attr: 'field-below',
        _field_class: 'normal-field-below',
        _field_type: '',
        _field_title: '',
        _additional_value_title: function(row_data){
            return _.escape(this._field_title);
        },
        _additional_value_template: function(value, row_data){
            var value = _.escape(formats.format_value(value, {type: this._field_type},  ''));
            return _.str.sprintf('<div class="%s" title="%s">%s</div>',this._field_class, this._additional_value_title(row_data), value);
        },
        _format: function (row_data, options) {
            var value;
            var field_below = this[this._field_attr];
            if (field_below && typeof field_below == 'string'){
//                value = row_data[field_below].value && row_data[field_below].value[1];
                value = row_data[field_below].value && row_data[field_below].value;
            }
            if (value) {
                return this._super(row_data, options) + this._additional_value_template(value, row_data);
            }
            return this._super(row_data, options);
        },

    });


    var ColumnAtostogosBelow = ColumnWithOtherFieldBelow.extend({
        _field_class: 'atostogos-field-below',
        _additional_value_title: function(row_data){
            var date_from = row_data['leave_date_from'] && row_data['leave_date_from'].value,
                date_to = row_data['leave_date_to'] && row_data['leave_date_to'].value;

            if (date_from && date_to){
                 return _.escape(moment(date_from).format('YYYY/MM/DD') + ' - ' + moment(date_to).format('YYYY/MM/DD'));
            }
            return _.escape(this._field_title);

        },
    });

    var ColumnRoboAnchor = Column.extend({
        _format: function(row_data, options) {
            return _.template('<a href="<%-href%>" class="<%-icon_class%>" title="<%-title%>" target="<%-target>"/>')(
                {
                    href: this.name && row_data[this.name].value || '#',
                    icon_class: 'btn btn-sm btn-link icon-location' + ' o_widgetonbutton o_is_posted',
                    title: _('Vykdyti'),
                    target: '_blank',
                });
        },
    });

    ListView.include({
        init: function(){
            this._super.apply(this, arguments);
            this.robo_front = this.ViewManager.robo_front;
            this.robo_fit = this.ViewManager.robo_fit;
        },
         /**
         * Instantiate and render the sidebar.
         * Sets this.sidebar
         * @param {jQuery} [$node] a jQuery node where the sidebar should be inserted
         * $node may be undefined, in which case the ListView inserts the sidebar in
         * this.options.$sidebar or in a div of its template
         **/
        render_sidebar: function($node) {
            if (!this.sidebar && this.options.sidebar) {
                this.sidebar = new Sidebar(this, {editable: this.is_action_enabled('edit')});
                if (this.fields_view.toolbar && !this.robo_front) {
                    this.sidebar.add_toolbar(this.fields_view.toolbar);
                }
                this.sidebar.add_items('other', _.compact([
                    !this.robo_front && { label: _t("Export"), callback: this.on_sidebar_export },
                    !this.robo_front && this.fields_view.fields.active && {label: _t("Archive"), callback: this.do_archive_selected},
                    !this.robo_front && this.fields_view.fields.active && {label: _t("Unarchive"), callback: this.do_unarchive_selected},
                    !this.robo_front && this.is_action_enabled('delete') && { label: _t('Delete'), callback: this.do_delete_selected }
                ]));

                $node = $node || this.options.$sidebar;
                this.sidebar.appendTo($node);

                // Hide the sidebar by default (it will be shown as soon as a record is selected)
                this.sidebar.do_hide();
            }
        },
    });

    var RoboTree = ListView.extend({
        _widgetName: 'Robo tree',
        _template: 'RoboListView',
        events: _.extend(ListView.prototype.events,
            {
                'change .o_checkbox': function (e) {
                    var row = e.target.parentElement.parentElement.parentElement;
                    var curr_index = this.$('tbody tr').index(row);
                    var shift_key_is_pressed = this.shiftKey;

                    if(shift_key_is_pressed && this.last_selected > -1) {
                        var last_selected_value = $($('tbody tr')[this.last_selected]).find('td.o_list_record_selector .o_checkbox input').prop('checked');
                        var curr_selected_value = $($('tbody tr')[curr_index]).find('td.o_list_record_selector .o_checkbox input').prop('checked');
                        var should_select = (curr_selected_value);
                        var rows_to_select = $('tbody tr').slice(
                            Math.min(this.last_selected, curr_index),
                            Math.max(this.last_selected, curr_index)+1
                        );
                        rows_to_select.find('td.o_list_record_selector .o_checkbox input').prop('checked', should_select);
                        rows_to_select.toggleClass('selected-row', should_select);
                        this.last_selected = -1;
                    } else {
                        var $selected_rows = this.$('tbody tr').has('input:checked');
                        var $not_selected_rows = this.$('tbody tr').has('input:not(:checked)');
                        $selected_rows.toggleClass('selected-row', true);
                        $not_selected_rows.toggleClass('selected-row', false);
                        this.last_selected = curr_index;
                    }
                },
                'click .box-active': function (e, view) {
                    e.preventDefault();
                    var id = $(e.currentTarget).data("id");
                    this._multi_open(id, true);
                },
                "keydown .o_checkbox": function (e) {
                    if (e.shiftKey) {
                        this.shiftKey = true;
                    }
                },
                "keyup .o_checkbox": function (e) {
                    // Shift key code is 16
                    if (e.keyCode == 16) {
                        this.shiftKey = false;
                    }
                },
        }),

        init: function() {
            this.last_selected = -1;
            this.shiftKey = false;
            this._super.apply(this, arguments);
        },
        /**
         * Render the buttons according to the ListView.buttons template and
         * add listeners on it.
         * Set this.$buttons with the produced jQuery element
         * @param {jQuery} [$node] a jQuery node where the rendered buttons should be inserted
         * $node may be undefined, in which case the ListView inserts them into this.options.$buttons
         * if it exists
         */
        render_buttons: function($node) {
            var add_button = !this.$buttons; // Ensures that this is only done once
            var result = this._super.apply(this, arguments);

            if (add_button) {
                if (this.robo_front && this.$buttons){
                  if (this.$buttons.find('.remove_item').length) {
                      this.$buttons.on('click', '.remove_item', this.do_delete_selected);
                  }
                  this.robo_front_actions = new RoboFrontActions(this);
                   if (this.fields_view.toolbar) {
                        this.robo_front_actions.add_toolbar(this.fields_view.toolbar);
                   }
                  this.robo_front_actions.appendTo(this.$buttons.find('ul.dropdown-menu li'));
                  this.$buttons.find('.btn-group').css("visibility", "hidden");
                  this.$buttons.find('.btn-group').css("display", "inline-block");
                }
            }
            return result
        },
        /**
         * Handles the signal indicating that a new record has been selected
         * Handles new tree button veiksmas
         *
         * @param {Array} ids selected record ids
         * @param {Array} records selected record values
         */
        do_select: function (ids, records, deselected) {
             if (!ids.length) {
                 if (this.$buttons.find('.btn-group').length){
                    this.$buttons.find('.btn-group').css("visibility", "hidden");
                 }
             }
             else{
                 if (this.$buttons.find('.btn-group').length){
                    this.$buttons.find('.btn-group').css("visibility", "visible");
                 }
             }
            this._super.apply(this, arguments);
        },
        do_action: function(){
          //force finish stack first before new action
            var _super = this._super.bind(this);
            var arg = arguments;
            _.delay(_.bind(function () {
                _super.apply(this, arg);
            }, this));
        },
        _multi_open_newId: function(new_id, action){
            this.do_action(action, {res_id: new_id});
        },
        /**
         * Handles the activation of a record (clicking on it) on a card or a table element
         *
         * @param {Object} id identifier of the activated record
         * @param {Object} is_card if a click on a card or table
         */
        _multi_open: function(id, is_card, index, view){
            var self = this;

            if (is_card) {
                if (_.isObject(this.read_action_new)) {
                    this.read_action_new.res_id = id;
                }
                else {
                    //possible cardOpen in action context not defined in action context;
                    this.do_warn(_t("Klaida"), _t(" Negalime atidaryti kortelės."));
                    return;
                }
            }

            if (!this.multi_open)
                is_card ? this.do_action(this.read_action_new):
                            this.select_record(index, view);
            else{
                try {
                    var action, done_once = false;
                    utils.async_when().then(function(){
                        var def = self.dataset.read_ids(
                            [id],
                            _.pluck(_(self.columns).filter(function (r) {
                                    return r.tag === 'field';
                                }), 'name')
                        );
                        return def;
                    }).then(function(record){
                        for(var i=0, len=self.multi_open.length; i<len && !done_once; ++i) {
                            var pair = self.multi_open[i],
                                action = pair[0],
                                expression = pair[1],
                                field = pair[3],
                                new_id = record[0][field][0] || record[0][field];
                            if (new_id > 0 && py.PY_isTrue(py.evaluate(expression, record[0]))) {
                                done_once = true;
                                self._multi_open_newId(new_id, action);
                            }
                        }
                        if (!done_once){
                            is_card ? self.do_action(self.read_action_new):
                                        self.select_record(index, view);
                        }
                    });
                }
                 catch(e){
                    this.do_warn(_t('Klaida'), _t('Nepavyko atidaryti formos iš '+ self._widgetName));
                    return;
                }
            }
        },

         /**
         * Handles the activation of a record (clicking on it)
          * opens multi_open action if there are specific fields with id (many2One?) and action
         *
         * @param {Number} index index of the record in the dataset
         * @param {Object} id identifier of the activated record
         * @param {instance.web.DataSet} dataset dataset in which the record is available (may not be the listview's dataset in case of nested groups)
         */
        do_activate_record: function (index, id, dataset, view) {
            this.dataset.ids = dataset.ids;
            this._multi_open(id, false, index, view);
        },

        willStart: function () {
            var self = this;
            var _super = this._super.bind(this);

            this.read_action_new = undefined;
            var loading_action;
            if (this.options && this.options.action && this.options.action.context && this.options.action.context.robo_create_new) {
                loading_action = data_manager.load_action(this.options.action.context.robo_create_new).then(function(action){
                    self.read_action_new = action;
                });
            }
            //read multiopen arch
            if (this.fields_view.arch.attrs.multi_open){
                this.multi_open= this.fields_view.arch.attrs.multi_open;
                this.multi_open = _(this.multi_open.split(';')).chain()
                    .compact()
                    .map(function(action_pair) {
                        var pair = action_pair.split(':'),
                            action = pair[0].trim(),
                            expr = pair[1].trim(),
                            field = pair[2].trim();
                        return [action, py.parse(py.tokenize(expr)), expr, field];
                    }).value();
            }

            return $.when(
                loading_action,
                self.recently_active_records(),
                _super()
            );
        },

        start: function(){
            //TODO: check if toggleClass animation should be somehow handled with promises
            var self = this;
            if (this.options && this.options.action && this.options.action.context){
                if (this.options.action.context.robo_subtype === 'expenses'){
                    this.$el.on('click', '.boxes-row .create-record.first-step', (function (_this) {
                            return function(e){
                                e.preventDefault();
                                e.stopPropagation();
                                var to_hide = _this.$('.first-step').add(_this.$('.box-active'));
                                to_hide.toggleClass('o_hidden', true, 400, 'swing');
                                _this.$('.second-step').toggleClass('o_hidden', false, 400, 'swing');
                            }
                        })(this)
                    );
                    this.$el.on('click', (function(_this){
                        return function(e){
                            if ($(e.target).closest('.box-invoice').length === 0){
                                var to_unhide = _this.$('.first-step').add(_this.$('.box-active'));
                                _this.$('.second-step').toggleClass('o_hidden', true, 400, 'swing');
                                to_unhide.toggleClass('o_hidden', false, 400, 'swing');
                            }
                        }
                    })(this));
                    var xml_id = '';
                    this.$el.on('click', '.boxes-row .create-record.second-step', (function(_this){
                        return function(e){
                          xml_id = $(e.currentTarget).data('xml-id');
                         if (xml_id && xml_id.trim())
                          _this.do_action(xml_id);
                        }
                    })(this));

                }
                else if (this.options.action.context.robo_create_new){
                    this.$el.on('click', '.boxes-row .create-record', function () {
                            self.do_action(self.options.action.context.robo_create_new);
                        }
                    );
                }
                else {
                    this.$el.on('click', '.boxes-row .create-record', this.proxy('do_add_record'));
                }
            }
            this.on('list_view_loaded', this, this._addTooltip);
            return $.when(this._super.apply(this, arguments));
        },
        _addTooltip: function(){
          this.$('[data-toggle=tooltip]:not([data-original-title])').tooltip();
        },
        recently_active_records: function () {
            var deferred = $.Deferred(), self = this;
            self.recently_active = [];
            if (!self.dataset.context.robo_template){ //no need of active records;
                return deferred.resolve().promise();
            }
            var myLimit = this.dataset.context && (this.dataset.context.limitActive || 3);
            var order_name = this.dataset.context.order_name || 'write_date';
            var domain = _.union(this.dataset.domain, this.dataset.context.activeBoxDomain);
            var domainForRecentActiveClients = []; // Domain to remove partners from display;
            if (this.dataset.context['robo_template'] == "RecentActiveClients"){
                domainForRecentActiveClients = ['|', ['email', 'not like', '%robolabs.lt'],
                                                '|', ['customer', '=', 'true'],['supplier', '=', 'true']];
            }
            new Model(this.dataset.model).query(this.fields_view.fields)
                .filter(domain).filter(domainForRecentActiveClients)
                .context({'is_force_order_time': true, 'force_order': this.dataset.context['force_order']})
                .order_by('-'+order_name) //most recent first or force order from context
                .limit(myLimit)
                .all()
                .then(function (records) {
                    _.each(records, function (record) {
                        self.recently_active.push(record);
                    });
                    deferred.resolve();
                }).then(function () {
                    var tfootRow = self.$('tfoot tr');
                    if (tfootRow.length == 1) {
                        tfootRow.children('td').each(function () {
                            var currentTdWidth = $(this).outerWidth();
                            $(this).css('min-width', currentTdWidth + 'px');
                        });
                    }
                 });
            return deferred;
        },
        load_list: function () {
            var self = this;
            var _super = this._super.bind(this);
            return $.when(self.recently_active_records()).then(function(){
                return _super();
            }).then(function(){
                 var state_names;
                 if (self.dataset.context && self.dataset.context.robo_template) {
                    if (self.fields_get && self.fields_get.state) {
                        state_names = _.object(self.fields_get.state.selection);
                    }
                    if (self.fields_get && self.fields_get.expense_state) {
                        state_names = _.extend(state_names, _.object(self.fields_get.expense_state.selection));
                    }
                    var infoBoxes = QWeb.render(self.dataset.context.robo_template, {
                        records: self.recently_active,
                        stateClass: state_colors,
                        stateNames: state_names || {},
                        format: roboUtils.format_LT_value,
                        getCurrency: function(v){return v;},
                        robo_subtype: self.dataset.context.robo_subtype,
                    });
                 return $.when($(infoBoxes).prependTo(self.$el));
                }
                return $.when()
            });
        },
        /**
         * Attaches for a column another's columns data. It is useful if you need during render_cell another's cell data.
         * user multi-col property to attach fields you want separated by ;
         *
         */
        setup_columns: function (fields, grouped) {
            var self = this;
            this._super.apply(this, arguments);

            _(self.columns).filter(function (col) {
                return !_.isEmpty(col['multi-col'])
            }).map(function(col){
               return col['multi-col'] = _(col['multi-col'].split(';')).chain()
                       .compact()
                       .map(function(el) {
                           var trimedEl = el.trim();
                           var addedCol = {};
                           addedCol[trimedEl] = _(self.columns).find(function (col) {
                                               return col.id === trimedEl;
                                                 });
                           return addedCol;
                       })
                       .compact()
                       .reduce(function(r,i){
                            var key = _.keys(i)[0];
                            r[key] = i[key];
                            return r;
                       },{})
                       .value();
            });
        },
        no_result: function () {

            this.$('.oe_view_nocontent').remove();
            this.$('.oe_view_robo_nocontent').remove();

            if (this.groups.group_by ||
                !this.options.action ||
                !(this.options.action.help || this.options.action.robo_help)) {
                return;
            }
            this.$('table:first').hide();

            if (!this.options.action.robo_help) {
                this.$el.prepend(
                    $('<div class="oe_view_nocontent">').html(this.options.action.help)
                );
            }
            else if (this.options.action.robo_help){
                this.$el.append(
                    $('<div class="oe_view_robo_nocontent">').html(this.options.action.robo_help)
                );
            }
        },
    });

    var RoboExpensesTree = RoboTree.extend({
        _widgetName: 'Robo expenses tree',
        _multi_open_newId: function (new_id, action) {
            var self = this;
            $.when(
                data_manager.load_action(action),
                new Model('hr.expense').query(['state']).filter([['id', '=', new_id]]).all()
            ).then(function (result, state) {
                if (state && state[0] && state[0].state == 'imported') {
                    result.flags.initial_mode = 'edit';
                }
                self.do_action(result, {res_id: new_id, 'hide_imported_payment_mode': true});
            });
        },
    });

    //slowdown game with filters
    search_input.FilterGroup.include({
        start: function() {
            this.$el.on('click', 'a', _.debounce(this.proxy('toggle_filter'),200));
            return $.when(null);
        },
    });

    var WebTreeImage = list_widget_registry.get('field.binary').extend({
        qweb_template: 'ListView.row.image',
        show_thumbnail_tooltip : function(row_data){},
        format: function (row_data, options) {
            /* Return a valid img tag. For image fields, test if the
             field's value contains just the binary size and retrieve
            the image from the dedicated controller in that case.
            Otherwise, assume a character field containing either a
            stock Odoo icon name without path or extension or a fully
            fledged location or data url */
            if (!row_data[this.id] || !row_data[this.id].value) {
                return '';
            }
            var value = row_data[this.id].value, src;
            if (this.type === 'binary') {
                if (value && value.substr(0, 10).indexOf(' ') === -1) {
                    // The media subtype (png) seems to be arbitrary
                    src = "data:image/png;base64," + value;
                } else {
                    var imageArgs = {
                        model: options.model,
                        field: this.id,
                        id: options.id
                    }
                    if (this.resize) {
                        imageArgs.resize = this.resize;
                    }
                    src = session.url('/web/binary/image', imageArgs);
                }
            } else {
                if (!/\//.test(row_data[this.id].value)) {
                    src = '/web/static/src/img/icons/' + row_data[this.id].value + '.png';
                } else {
                    src = row_data[this.id].value;
                }
            }

            var title = this.show_thumbnail_tooltip(row_data) ? _.template('<img src="<%-src%>"/>')({src: src}) : '';
            return QWeb.render(this.qweb_template, {widget: this, src: src, title: title});
        }
    });

    var WebTreeDocumentImage = WebTreeImage.extend({
        qweb_template: 'ListView.row.document_image',
        show_thumbnail_tooltip: function(row_data){
            var show = false;
            if (row_data['thumbnail_force_enabled'] && row_data['thumbnail_force_enabled'].value){
                show = true;
            }
            return show
        },
    });

    var HtmlWarningIcon = Column.extend({
        _format: function(row_data){
            var _state_field = 'html_warning_icon'
            var value = row_data[_state_field] && row_data[_state_field].value;
            if(!_.isEmpty(value)){
                   return value;
            }
            return '';
        },
    });

    list_widget_registry.add('field.image', WebTreeImage);
    list_widget_registry.add('field.document_image', WebTreeDocumentImage);

    core.view_registry.add('tree_expenses_robo', RoboExpensesTree);
    core.view_registry.add('tree_robo', RoboTree);
    list_widget_registry.add('field.htmlToText', ColumnHtmlToText);
    list_widget_registry.add('field.expenseType_boolean', ColumnExpenseType);
    list_widget_registry.add('field.roboStatus', ColumnState);
    list_widget_registry.add('field.roboUploadState', ColumnUploadState);
    list_widget_registry.add('field.roboStateIcon', ColumnWithIcon);
    list_widget_registry.add('field.roboAddState', ColumnAddState);
    list_widget_registry.add('field.BankExportState', BankExportState);
    list_widget_registry.add('field.roboInvoiceState', ColumnInvoiceState);
    list_widget_registry.add('field.roboAddStateExp', ColumnAddStateExp);
    list_widget_registry.add('field.roboFieldBelow', ColumnWithOtherFieldBelow);
    list_widget_registry.add('field.roboFieldBelowAtostogos', ColumnAtostogosBelow);
    list_widget_registry.add('field.roboAnchor', ColumnRoboAnchor);
    list_widget_registry.add('field.HtmlWarningIcon', HtmlWarningIcon);

    return RoboTree;
});
