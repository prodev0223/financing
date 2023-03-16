robo.define('account_dynamic_reports.DynamicReportDataController', function(require) {
    
    'use strict';
    
    var Core = require('web.core');
    var Widget = require('web.Widget');
    var Model = require('web.Model');
    var WebClient = require('web.web_client');
    var Session = require('web.session');
    var Formats = require('web.formats');
    var QWeb = Core.qweb;
    var _t = Core._t;

    return Widget.extend({
        template: 'DynamicReportDataSection',
        events: {
            'click .column-header': 'updateSortingOrder',
            'click .data-row-with-action': 'openDataRowAction',
            'click .group-title-row': 'toggleGroupCollapse',
            'click .toggle_child_elements_button': 'toggleChildElements',
        },
        init: function (parent, options) {
            this._super(parent, options);
            this.dynamicReportController = parent;
            this.wizardId = this.dynamicReportController.wizardId | null;
            this.widgetModel = this.dynamicReportController.widgetModel || 'dynamic.report';
            this.displayName = this.dynamicReportController.title || _t('Dynamic report');
            this.sortingData = {column: 0, direction: 'ascending'};
            this.columnData = [];
        },
        start: function () {
            this._super.apply(arguments);
            return this.refreshData();
        },


        // DATA FUNCTIONS
        refreshData: async function () {
            var self = this;
            this.dynamicReportController.disableUI();
            await self.getColumnData();
            return new Model(self.widgetModel).call('get_render_data', [[self.wizardId]]).then(
                function (renderData) {
                    Promise.resolve($.when(self.renderDataTable(renderData)).then(function (renderedTable) {
                        self.loadData(renderedTable)
                    }));
                    self.dynamicReportController.enableUI();
                }
            ).fail(function(){ self.dynamicReportController.enableUI(); });
        },
        getColumnData: async function() {
            var promise = $.Deferred();
            var self = this;
            new Model(self.widgetModel).call('get_shown_column_data', [[self.wizardId]]).then(
                function (columnData) {
                    self.columnData = columnData;
                    promise.resolve(columnData);
                }
            );
            return promise;
        },
        loadData: function (report_html) {
            var dataContainer = this.$();
            dataContainer.empty();
            dataContainer.append(report_html);
            this.setSortByCaret();
            this.createGroupExpandIcons();
        },
        getGroupRowTemplate: function() {
            return "DynamicReportGroupTitleRow"
        },
        getDataRowTemplate: function() {
            return "DynamicReportGroupDataRow"
        },
        getTableTemplate: function() {
            return "DynamicReportTable"
        },
        renderDataTable: function (renderData) {
            var renderedGroupData = this.renderGroupData(renderData);
            return QWeb.render(this.getTableTemplate(), {
                'columns': this.columnData,
                'renderedGroupData': renderedGroupData,
                'any_child_has_child_elements': renderData.any_child_has_child_elements,
                'max_group_level': renderData.max_group_level,
                'group_totals': renderData.group_totals,
            });
        },
        renderDataRow: function(rowData) {
            rowData['renderMonetaryValue'] = this.renderMonetaryValue;
            // Don't render empty rows
            if (rowData.cells.every(cell => { return !cell.value || cell.value === ''})) { return ''}
            return QWeb.render(this.getDataRowTemplate(), rowData);
        },
        renderGroupData: function(renderData) {
            var self = this;
            var renderedGroup = ''

            // Render group title
            const groupTitle = renderData.group_title || '';
            const groupTitleRow = QWeb.render(self.getGroupRowTemplate(), renderData)

            // Render subgroups
            const subgroups = renderData.subgroups || [];
            var renderedSubgroups = '';
            subgroups.forEach(subgroup => { renderedSubgroups += self.renderGroupData(subgroup); });
            renderedGroup += renderedSubgroups;

            // Render data rows
            const dataRows = renderData.children || [];
            var renderedDataRows = '';
            dataRows.forEach((dataRow, index) => {
                dataRow['oddRow'] = index % 2 !== 0
                renderedDataRows += self.renderDataRow(dataRow);
            });
            renderedGroup += renderedDataRows

            // Determine if the group title row (containing group totals) should go at the top of the data or at the bottom
            if (groupTitle) {
                renderedGroup = groupTitleRow + renderedGroup
            } else {
                renderedGroup += groupTitleRow
            }

            return renderedGroup
        },


        // GROUPING FUNCTIONS
        createGroupExpandIcons: function () {
            $('.group_title_container').each(function(el) {
                var rowGroupLevel = $(this).closest('tr.group-title-row').attr('group-level');
                if (rowGroupLevel === "-1" || !rowGroupLevel) { return; }
                $(QWeb.render('DynamicReportGroupExpandCaret')).prependTo( this );
            });
        },



        // SORTING FUNCTIONS
        getNewSortingOrder: function(event) {
            const columnHeader = $(event.target).closest('th.column-header')
            const columnRow = columnHeader.parent();
            const numberOfEmptyCells = columnRow.children('.empty-cell').length;
            const sortByIndex = columnHeader.index() - numberOfEmptyCells;
            var direction = 'ascending'
            if (sortByIndex < 0) { return {
                column: 0,
                direction: direction,
            }} // Header not found

            const currentColumnIndex = this.sortingData.column;
            
            if (currentColumnIndex === sortByIndex) {
                direction = (this.sortingData.direction === 'ascending') ? 'descending' : 'ascending';
            }

            return {
                column: sortByIndex,
                direction: direction,
            };
        },
        storeSortingOrder: async function() {
            var self = this;
            var promise = $.Deferred();
            new Model(self.widgetModel).call('store_sorting_data', [[self.wizardId], self.sortingData]).then(
                function () { promise.resolve(); }
            );
            return promise
        },
        updateSortingOrder: async function(event) {
            var sortingOrder = this.getNewSortingOrder(event);
            this.sortingData = sortingOrder;
            this.setSortByCaret();
            await this.storeSortingOrder();
            return this.refreshData();
        },
        setSortByCaret: function() {
            // Reset current arrows
            var sortingArrows = $(this.el).find('.sorting-arrow');
            sortingArrows.toggleClass('sorting-arrow-active', false);
            sortingArrows.toggleClass('fa-caret-up', false);
            sortingArrows.toggleClass('sorting-arrow-inactive', true);
            sortingArrows.toggleClass('fa-caret-down', true);

            // Find element to set caret on
            var columnElements = $(this.el).find('th.column-header').not('.empty-cell')
            var currentHeaderElement = columnElements[this.sortingData.column];

            // Add sorting arrow
            var sortingArrow = $(currentHeaderElement).find('.sorting-arrow');
            $(sortingArrow).toggleClass('sorting-arrow-active', true);
            if (this.sortingData.direction === 'ascending') {
                $(sortingArrow).toggleClass('fa-caret-down', false);
                $(sortingArrow).toggleClass('fa-caret-up', true);
            }
        },




        findSiblingRowRecords: function(row) {
            if (!row) { return }
            var self = this;
            var action = row.attr('action');
            var rowRecords = row.attr('record');
            if (!action || !rowRecords) { return }

            var records = this.parseRowRecords(rowRecords);

            var siblingAction = null;
            var siblingRecord = null;

            var previousSibling = $(row).prev();
            while (previousSibling && previousSibling.hasClass('data-row-with-action')) {
                siblingAction = previousSibling.attr('action');
                siblingRecord = previousSibling.attr('record');
                if (siblingAction === action && siblingRecord) {
                    records.concat(self.parseRowRecords(siblingRecord));
                    previousSibling = previousSibling.prev();
                } else { previousSibling = null; }
            }

            var nextSibling = $(row).next();
            while (nextSibling && nextSibling.hasClass('data-row-with-action')) {
                siblingAction = nextSibling.attr('action');
                siblingRecord = nextSibling.attr('record');
                if (siblingAction === action && siblingRecord) {
                    records.concat(self.parseRowRecords(siblingRecord));
                    nextSibling = nextSibling.next();
                } else { nextSibling = null; }
            }

            return records
        },
        parseRowRecords: function(records) {
            var result = [];
            if (!records || records.length === 0) { return result }
            records = records.split(',')
            if (!records || records.length === 0) { return result }
            records.forEach(record => {
                result.push(parseInt(record, 10));
            })
            return result
        },
        openDataRowAction: function(event) {
            var self = this;
            var target = $(event.target);
            if (target && target.length && (target.hasClass('toggle_child_elements_button') || target.parent().hasClass('toggle_child_elements_button'))) { return ;}
            var row = $(target).closest('tr')
            var action = row.attr('action');
            var rowRecords = row.attr('record');
            rowRecords = this.parseRowRecords(rowRecords);
            if (!action) { return }

            var records = self.findSiblingRowRecords(row);

            if (!records || records.length === 0) { records = rowRecords; }

            if (!records || records.length === 0) { return }

            self.rpc("/web/action/load", { action_id: action }).done(function(action) {
                if (_.isObject(action)) {
                    if (rowRecords && rowRecords.length == 1) { action['res_id'] = rowRecords[0]; }

                    // Check if the action has a form view mode or has a form view and if it does - set the view type
                    // to form view.
                    var hasFormView = false;
                    var viewModes = action.hasOwnProperty('view_mode') && action['view_mode'];
                    var actionViews = action.hasOwnProperty('views') && action['views'];
                    var viewModesAreSet = viewModes && viewModes.length > 0 &&
                                            (typeof viewModes === 'string' || viewModes instanceof String);
                    var actionFormViews = actionViews &&
                                            actionViews.filter(function (actionView) {
                                                return actionView.length > 1 && actionView[1] === 'form' }
                                            );
                    if ((viewModesAreSet && viewModes.replace(' ', '').split(',').includes('form')) || actionFormViews){
                        hasFormView = true;
                    }
                    var actionContext = action.hasOwnProperty['context'] ? action['context'] : {};
                    if (hasFormView && rowRecords.length == 1) { actionContext['view_type'] = 'form'; }

                    action['target'] = 'current';
                    action['domain'] = [['id', 'in', records]];

                    WebClient.do_notify(
                        _t("Redirected to record"),
                        _t("You have been redirected to the selected record. To go back - please click on the link " +
                           "at the top.")
                    );
                    self.do_action(action, actionContext);
                }
            });
        },
        toggleGroupCollapse: function(event) {
            var groupRow = $(event.target.closest('tr.group-title-row'));
            if (!groupRow) { return }
            var rowGroupLevel = groupRow.attr('group-level');
            if (!rowGroupLevel || rowGroupLevel === "-1") { return }

            var action = groupRow.hasClass('data-group-expanded') ? 'collapse' : 'expand';
            var groupExpandIcon = groupRow.find('.group-expand-icon');
            if (groupExpandIcon.length) {
                groupExpandIcon.toggleClass('fa-caret-down', action === 'expand');
                groupExpandIcon.toggleClass('fa-caret-right', action !== 'expand');
            }


            var rowGroup = groupRow.attr('group');

            var elementToModify = groupRow.next();
            var nextRowIsSameGroupRow = elementToModify && elementToModify.hasClass('group-title-row') && elementToModify.attr('group') === rowGroup;
            if (nextRowIsSameGroupRow) { action = elementToModify.hasClass('data-group-expanded') ? 'collapse' : 'expand'; }
            groupRow.toggleClass('data-group-expanded', action === 'expand');
            var lastGroupLevelToKeepCollapsed = null;
            var elementGroupIsCollapsed = action == 'collapse';
            while (elementToModify) {
                var elementGroupLevel = elementToModify.attr('group-level');
                var elementGroup = elementToModify.attr('group');
                var elementIsGroupRow = elementToModify.hasClass('group-title-row');
                var elementIsSameOrHigherLevelGroup = !elementGroupLevel || elementGroupLevel > rowGroupLevel;
                var isSameGroupTitleRow = elementIsGroupRow && rowGroup === elementGroup;
                if (isSameGroupTitleRow) {
                    elementToModify.toggleClass('data-group-expanded', action === 'expand');
                    elementToModify = elementToModify.next();
                    continue; // When title rows span two rows due to totals being calculated
                }
                if (!elementIsSameOrHigherLevelGroup) { break }

                var elementIsCollapsedGroup = elementIsGroupRow && !elementToModify.hasClass('data-group-expanded');

                if (elementIsCollapsedGroup) { lastGroupLevelToKeepCollapsed = elementGroupLevel }

                var elementAction = action;
                if (elementAction === 'expand' && lastGroupLevelToKeepCollapsed && lastGroupLevelToKeepCollapsed <= elementGroupLevel && !elementIsGroupRow) {
                    elementAction = 'collapse'; // Force keep group collapsed if parent group element is collapsed.
                }

                var hideRow = elementAction == 'collapse';
                if (!hideRow && !elementIsGroupRow && elementGroupIsCollapsed) {
                    hideRow = true;
                }

                elementToModify.toggleClass('data-row-collapsed', hideRow);

                if (elementIsGroupRow) {
                    lastGroupLevelToKeepCollapsed = elementGroupLevel;
                    groupExpandIcon = elementToModify.find('.group-expand-icon');
                    elementGroupIsCollapsed = groupExpandIcon.hasClass('fa-caret-right');
                }

                elementToModify = elementToModify.next();
            }
        },
        toggleChildElements: function(event) {
            var target = $(event.target);
            var iconElement = target.closest('.toggle_child_element_icon');
            var action = iconElement.hasClass('fa-bars') ? 'open' : 'close';
            iconElement.toggleClass('fa-bars', action == 'close');
            iconElement.toggleClass('fa-times', action == 'open');
            var nextRow = target.parent().parent().next();
            while (nextRow && nextRow.length && nextRow.hasClass('child_row')) {
                nextRow.toggleClass('hidden', action == 'close');
                nextRow = nextRow.next();
            }
        },
        renderMonetaryValue: function(value, currency_id) {
            var currency = Session.get_currency(currency_id);
            var digits_precision = currency && currency.digits;
            value = Formats.format_value(value || 0, {type: "float", digits: digits_precision});
            if (currency) {
                if (currency.position === "after") {
                    value += currency.symbol;
                } else {
                    value = currency.symbol + value;
                }
            }
            return value;
        },
    })

});