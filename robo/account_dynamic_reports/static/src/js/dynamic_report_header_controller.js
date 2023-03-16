robo.define('account_dynamic_reports.DynamicReportHeaderController', function(require) {
    
    'use strict';

    const Core = require('web.core');
    const Widget = require('web.Widget');
    const Model = require('web.Model');
    const QWeb = Core.qweb;
    const _t = Core._t;

    return Widget.extend({
        template: 'DynamicReportFilterSection',
        events: {
            'click #filter_apply_button': 'refreshReport',
            'change .date_filter-multiple': 'updateDateRange',
            'change #date_from': 'resetDateRange',
            'change #date_to': 'resetDateRange',
            'click #pdf': 'exportPDF',
            'click #xlsx': 'exportXLSX',
            'click #report_settings': 'openReportSettings',
            'change .other_filters-multiple': 'adjustShownFilterSelection',
//            'change .dynamic-report-group-by-button select': 'refreshReport',
        },
        init: function (parent, options) {
            this._super(parent, options);
            this.dynamicReportController = parent;
            this.wizardId = this.dynamicReportController.wizardId | null;
            this.widgetModel = this.dynamicReportController.widgetModel || 'dynamic.report';
            this.displayName = this.dynamicReportController.title || _t('Dynamic report');
            this.filterData = null;
            this.dateFormat = 'YYYY-MM-DD';
            this.dateParseFormat = 'yy-mm-dd';
            this.headerDateSections = [];
            this.headerFilterSections = [];
            this.groupByData = [];
            this.updatingDateRange = false;
            this.enableReportSettings = this.dynamicReportController.enableReportSettings;
        },
        willStart: async function() {
            this._super.apply(arguments);
            await this.getFilterFields();
            await this.getGroupByData();

            this.setUpFilterFields();
            return this.setStoredFilterValues();
        },
        start: function () {
            this._super.apply(arguments);
            return $.when(
                this.setUpSelectionFields()
            ).then(
                this.updateSelectedGroupByFields()
            ).then(
                this.refreshHeader(false)
            );
        },
        getFilterFields: async function () {
            var self = this;
            var promise = $.Deferred();
            new Model(this.widgetModel).call('get_filters', [this.wizardId]).then(function (filterData) {
                self.filterData = filterData['field_filters'];
                promise.resolve(filterData);
            });
            return promise;
        },
        getGroupByData: async function () {
            var self = this;
            var promise = $.Deferred();
            new Model(this.widgetModel).call('get_enabled_group_by_data', [this.wizardId]).then(function (groupByData) {
                self.groupByData = groupByData;
                promise.resolve(groupByData);
            });
            return promise;
        },
        setUpFilterFields: function () {
            // Sets up field filters by loading filter fields on the view using QWeb templates.
            var self = this;
            const filterFields = this.filterData || {};
            const filterFieldNames = this.getFieldNames();

            // Add date range selection to view
            const hasDateFromAndDateTo = filterFieldNames.includes('date_from') && filterFieldNames.includes('date_to');
            if (hasDateFromAndDateTo) { this.headerDateSections.push(QWeb.render('DateRangeSelection')) }

            // Render filter fields
            filterFieldNames.forEach(function (fieldName) {
                const fieldAttributes = filterFields[fieldName];
                const fieldType = fieldAttributes['type'];
                const isSelectionField = ['many2one', 'selection', 'boolean', 'many2many'].includes(fieldType);
                const isNumberField = ['integer', 'float'].includes(fieldType)
                const isDateField = fieldType === 'date';
                if (isSelectionField) {
                    // Render selection filter field
                    self.headerFilterSections.push(QWeb.render('SelectionFilter', {
                        filter_field: fieldAttributes,
                    }));
                } else if (isDateField) {
                    // Render date filter field
                    self.headerDateSections.push(QWeb.render('DateFieldFilter', {
                        filter_field: fieldAttributes,
                    }));
                } else if (isNumberField) {
                    self.headerFilterSections.push(QWeb.render('NumberFilter', {
                        filter_field: fieldAttributes,
                    }));
                }
            });
        },
        refreshHeader: async function (getFiltersAndGroupByFields=true) {
            if (getFiltersAndGroupByFields) {
                await this.getFilterFields();
                await this.getGroupByData();
                this.updateSelectedGroupByFields();
                return this.setStoredFilterValues();
            }
            return this.setStoredFilterValues();
        },
        getFieldNames: function(sort=true) {
            // Get filter fields and sort them by field string
            const filterFields = this.filterData || {};
            var filterFieldNames = Object.keys(filterFields);
            if (!sort) { return filterFieldNames }
            filterFieldNames.sort((firstField, secondField) => {
                if (firstField.includes('date') || secondField.includes('date')) {
                    // Make sure date fields are ordered by their field name
                    if (firstField < secondField) {
                        return -1
                    } else if (firstField > secondField) {
                        return 1
                    }
                    return 0
                }
                const firstFieldAttributes = filterFields[firstField];
                const secondFieldAttributes = filterFields[secondField];

                // Sort fields by their types
                const fieldTypePriorities = [
                    'integer', 'float', 'string', 'many2many', 'one2many', 'many2one', 'selection', 'boolean', 'bool'
                ];
                const firstFieldTypePriority = fieldTypePriorities.indexOf(firstFieldAttributes.type || '');
                const secondFieldTypePriority = fieldTypePriorities.indexOf(secondFieldAttributes.type || '');
                if (firstFieldTypePriority < secondFieldTypePriority) { return -1 }
                if (firstFieldTypePriority > secondFieldTypePriority) { return 1 }

                // If types match - sort by name
                const firstFieldString = (firstFieldAttributes.string || firstField).toUpperCase();
                const secondFieldString = (secondFieldAttributes.string || secondField).toUpperCase();
                if (firstFieldString < secondFieldString) {
                    return -1
                } else if (firstFieldString > secondFieldString) {
                    return 1
                }
                return 0
            });
            return filterFieldNames;
        },
        setUpSelectionFields: function() {
            // Used for setting up fields using select2 library if they exist
            var self = this;

            const filterFields = this.filterData || {};
            const filterFieldNames = this.getFieldNames();

            
            var classSelect2OptionMap = {};

            // Add options for date filter field
            const hasDateField = filterFieldNames.some(ffn => ['date_from', 'date_to'].includes(ffn));
            if (hasDateField) {
                classSelect2OptionMap['date_filter-multiple'] = {
                    maximumSelectionSize: 1,
                    placeholder: _t('Select period...'),
                };
            }

            // Add options for each filter field
            filterFieldNames.forEach(function (fieldName) {
                const fieldAttributes = filterFields[fieldName];
                const fieldType = fieldAttributes['type'];
                const isSelectionField = ['many2one', 'selection', 'boolean', 'many2many'].includes(fieldType);
                if (isSelectionField) {
                    // Add selection field to select2 class option map to set up later
                    let selection_class = fieldAttributes['name'] + '-multiple';
                    classSelect2OptionMap[selection_class] = {
                        placeholder: _t('Select...'),
                    }
                    if (!fieldAttributes['allow_selecting_multiple']) {
                        // If field doesn't have allow_selecting_multiple set as true - limit the selection size to one.
                        classSelect2OptionMap[selection_class]['maximumSelectionSize'] = 1;
                    }
                }
            });

            // Add options for group by field
            classSelect2OptionMap['py-group-by-menu'] = {placeholder: _t('Select...'),};

            // Loop through fields with each class and apply select2 with options
            for (const [className, options] of Object.entries(classSelect2OptionMap)) {
                const fullClassName = '.' + className;
                const elementsWithClass = self.$el.find(fullClassName);
                elementsWithClass.each(function () {
                    $(this).select2(options);
                });
            }

            // Set up date pickers
            const dateTimePickerOptions = {pickTime: false, format: self.dateFormat};
            this.$el.find('.dynamic_report_datepicker').each(function () {
                $(this).datetimepicker(dateTimePickerOptions);
            });
        },
        setStoredFilterValues: function () {
            // Updates header selections and inputs with values from filterData
            const filterFieldNames = this.getFieldNames();
            var self = this;
            filterFieldNames.forEach(function (fieldName) {
                self.setStoredFilterValue(fieldName);
            });
        },
        setStoredFilterValue: function (fieldName) {
            const filterFields = this.filterData || {};
            const fieldAttributes = filterFields[fieldName];

            const isDateField = fieldAttributes.type === 'date';

            const elementSelector = this.getElementSelector(fieldName);
            const elementsBySelector = this.$el.find(elementSelector);
            const currentValues = fieldAttributes['current_value'];

            var valueToSet = currentValues;

            if (!fieldAttributes['allow_selecting_multiple']) {
                valueToSet = (currentValues && currentValues.length > 0) ? currentValues[0] : false;
            }

            valueToSet = (isDateField && !valueToSet) ? '' : valueToSet  // Condition so that 'false' is not set on date fields.
            const dateToSet = (isDateField && valueToSet !== '') ? new Date(valueToSet) : false

            elementsBySelector.each(function () {
                $(this).val(valueToSet)
                if (dateToSet) { $(this).data("DateTimePicker").setDate(dateToSet); }
                $(this).trigger('change');
            });
        },
        storeFilterValues: async function () {
            const currentFilterValues = this.getCurrentFilterValues()
            if (!currentFilterValues) { return }
            var self = this;
            var result = $.Deferred();
            $.when(new Model(this.widgetModel).call('update_report_filters', [[self.wizardId], currentFilterValues])).then(
                function () {
                    self.refreshHeader();
                    result.resolve();
                }
            ).fail(self.dynamicReportController.enableUI());
            return result
        },
        storeGroupBySelection: async function () {
            var result = $.Deferred();
            var self = this;
            var currentlySelectedGroupByFields = self.getSelectedGroupByFields();
            $.when(new Model(this.widgetModel).call('update_group_by_selection', [[self.wizardId], currentlySelectedGroupByFields])).then(
                function () {
                    result.resolve();
                }
            ).fail(self.dynamicReportController.enableUI());;
            return result
        },
        refreshReport: async function(event) {
            event.preventDefault();
            this.dynamicReportController.disableUI();
            try {
                await this.storeFilterValues();
                await this.storeGroupBySelection();
                await this.refreshData();
            } catch (error) {
                this.dynamicReportController.enableUI();
            }
        },
        getElementSelector: function(fieldName) {
            const filterData = this.filterData || {};
            const fieldAttributes = filterData[fieldName];
            const isDateField = fieldAttributes.type === 'date';
            const isNumberField = ['integer', 'float'].includes(fieldAttributes.type);
            if (isNumberField) { return '.' + fieldName + '-input';}
            return isDateField ? '#' + fieldName : '.' + fieldName + '-multiple';
        },
        getCurrentFilterValues: function () {
            // Gets what filter values have been enabled
            var self = this;

            var enabledFilters = {};
            var filterFields = this.filterData || {};

            if (!filterFields) { return enabledFilters }

            const filterFieldNames = Object.keys(filterFields);

            filterFieldNames.forEach(function (fieldName) {
                enabledFilters[fieldName] = self.getSetFilterValue(fieldName);
            });

            return enabledFilters;
        },
        getSetFilterValue: function(fieldName) {
            const self = this;

            const filterData = this.filterData || {};
            const fieldAttributes = filterData[fieldName];
            var possibleSelectionValues = [];
            try {
                possibleSelectionValues = fieldAttributes.list_of_values.map(selectionData => {return selectionData[0]});
            } catch (error) {
                possibleSelectionValues = [];
            }

            const isDateField = fieldAttributes.type === 'date';
            const isNumberField = ['integer', 'float'].includes(fieldAttributes.type);

            const elementSelector = this.getElementSelector(fieldName);
            const elementsBySelector = self.$el.find(elementSelector);
            if (elementsBySelector.length < 1) { return }
            const filterElement = $(elementsBySelector[0]);

            var elementValue = false;

            if (isDateField && filterElement.val()) {
                const dateElement = filterElement.data("DateTimePicker");
                const dateObject = dateElement.getDate().toDate();
                if (dateObject) { elementValue = $.datepicker.formatDate(self.dateParseFormat, dateObject); }
            } else if (isNumberField) {
                 elementValue = filterElement.val();
            } else if (!isDateField) {
                elementValue = [];
                const selectData = filterElement.select2('data');
                if (fieldAttributes['allow_selecting_multiple']) {
                    for (let selectElement of selectData) {
                        elementValue.push(parseInt(selectElement.id) || selectElement.id);
                    }
                } else {
                    // Check if the selection is in possible selections and if it is - don't try to parse the selection
                    // as a number
                    var tryToGetInt = possibleSelectionValues.length > 0 && possibleSelectionValues.indexOf(selectData.id) === -1;
                    var selection = tryToGetInt ? (parseInt(selectData.id) || selectData.id) : selectData.id;
                    elementValue.push(selection);
                }
            }
            return elementValue;
        },
        updateDateRange: function(event) {
            // When changing the date range update the date from and date to fields if they exist
            var self = this;
            var currentValue = event.currentTarget.value;
            if (!currentValue || self.updatingDateRange) {
                self.updatingDateRange = false;
                return;
            }
            $.when(
                new Model(self.widgetModel).call('get_dates_from_range', [currentValue])
            ).then(function (dateRange) {
                if (dateRange.length !== 2) {
                    return;
                }
                var date_from_field = $.find(' #date_from ');
                var date_to_field = $.find(' #date_to ');
                if (date_from_field.length) {
                    date_from_field = $(date_from_field);
                    date_from_field.val(dateRange[0]);
                    date_from_field.data("DateTimePicker").setDate(new Date(dateRange[0]));
                }
                if (date_to_field.length) {
                    date_to_field = $(date_to_field);
                    date_to_field.val(dateRange[1]);
                    date_to_field.data("DateTimePicker").setDate(new Date(dateRange[1]));
                }
            });
        },
        resetDateRange: function(event) {
            var self = this;
            var date_range_selection_field = $(' select.date-range-input ');
            if (!date_range_selection_field.length) {
                date_range_selection_field.val("").change();
                return
            }
            var date_from_field = $.find(' #date_from ');
            var date_to_field = $.find(' #date_to ');
            var date_from = date_from_field.length == 1 ? $(date_from_field).val() : false;
            var date_to = date_to_field.length == 1 ? $(date_to_field).val() : false;
            if (!date_from || !date_to) {
                date_range_selection_field.val("").change();
                return
            }
            $.when(
                new Model(self.widgetModel).call('get_date_range_from_dates', [date_from, date_to])
            ).then(function (dateRange) {
                self.updatingDateRange = true;
                dateRange = dateRange ? dateRange : "";
                date_range_selection_field.val(dateRange).change();
            });
        },
        exportPDF: function(event) {
            event.preventDefault();
            var self = this;
            if (!this.widgetModel || !this.wizardId) { return; }
            return new Model(self.widgetModel).call('action_pdf', [[self.wizardId]]).then(
                function(action) { 
                    return self.do_action(action);
                }
            );
            
        },
        exportXLSX: function(event) {
            event.preventDefault();
            var self = this;
            if (!self.widgetModel || !self.wizardId) { return; }
            return new Model(self.widgetModel).call('action_xlsx', [[self.wizardId]]).then(
                function(action) {
                    try {
                        // Try to set the active id
                        action.context.active_ids = [self.wizardId];
                    } catch (error) {}
                    return self.do_action(action);
                }
            );
        },
        openReportSettings: function(event) {
            event.preventDefault();
            var self = this;
            return new Model(self.widgetModel).call('action_open_report_settings', [[self.wizardId]]).then(function (action) {
                self.do_action(action, {on_close: function() { self.refreshData(); }});
            });
        },
        getSelectedGroupByFields: function() {
            var self = this;
            var groupBySelectElement = self.$el.find('.py-group-by-menu').first();
            var selectData = groupBySelectElement.length ? groupBySelectElement.select2('data') : [];
            var groupByData = [];
            for (let selectElement of selectData) {
                groupByData.push(selectElement.id);
            }
            return groupByData;
        },
        refreshData: async function() {
            var self = this;
            var result = $.Deferred();
            $.when(self.dynamicReportController.refreshData()).then(function () {
                result.resolve();
            }).fail(self.dynamicReportController.enableUI());;
            return result
        },
        updateSelectedGroupByFields: function() {
            var self = this;
            var groupByIdentifiers = [];
            var selectedIdentifiers = this.groupByData.forEach(groupByData => {
                if (groupByData.selected) { groupByIdentifiers.push(groupByData.id) }
            })
            var groupBySelector = $('select.py-group-by-menu');
            if (groupBySelector.length != 1) { return }

            var sortedGroupByData = self.groupByData.sort((a, b) => {
                var index_of_a = groupByIdentifiers.indexOf(a.value);
                var index_of_b = groupByIdentifiers.indexOf(b.value);
                return index_of_a == index_of_b ? 0 : index_of_a < index_of_b ? -1 : 1;
            });

            $(groupBySelector).find('option').remove();

            sortedGroupByData.forEach(function(groupByField) {
                groupBySelector.append($('<option>', {
                    value: groupByField['id'],
                    text: groupByField['name']
                }));
            });

            groupBySelector.val(groupByIdentifiers).trigger('change');
        },
        adjustShownFilterSelection: function(event) {},
    })

});