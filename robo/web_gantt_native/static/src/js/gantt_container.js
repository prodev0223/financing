robo.define('web_gantt_native.GanttContainer', function (require) {
"use strict";

var core = require('web.core');
var formats = require('web.formats');
var Model = require('web.Model');
var data = require('web.data');
var time = require('web.time');
var View = require('web.View');
var form_common = require('web.form_common');
var Dialog = require('web.Dialog');

var utils = require('web.utils');

var session = require('web.session');


var GanttTimeLineHead = require('web_gantt_native.TimeLineHead');
var GanttTimeLineHeader = require('web_gantt_native.TimeLineHeader');
var GanttTimeLineScroll = require('web_gantt_native.TimeLineScroll');

var GanttListItem =     require('web_gantt_native.Item');
var GanttTimeLineData = require('web_gantt_native.TimeLineData');

var GanttTimeLineArrow = require('web_gantt_native.TimeLineArrow');

var GanttItemSorted = require('web_gantt_native.Item_sorted');

var GanttToolField = require('web_gantt_native.ToolField');

var GanttTimeLineGhost = require('web_gantt_native.Ghost');
var GanttTimeLineSummary = require('web_gantt_native.Summary');
var GanttTimeLineFirst = require('web_gantt_native.BarFirst');


var _t = core._t;
var _lt = core._lt;
var QWeb = core.qweb;


    // View.include({
    //
    // destroy: function () {
    //     if (!this.gantt_timeline_header_widget) {
    //
    //         var ctrl_panel = $('.timeline-gantt-h-scroll');
    //
    //
    //         // this.gantt_timeline_header_widget = [];
    //     }
    //     return this._super.apply(this, arguments);
    // },
    //
    // });

var GanttContainer = View.extend({
    display_name: _lt('Gantt APS'),
    icon: 'fa-tasks',
    template: 'GanttContainerView',
    view_type: 'ganttaps',

    events: {
        'mousedown .task-gantt-gutter': 'GutterMouseDown',
        // 'click .task-gantt-zoom-1h': 'Zoom1hClick',
        // 'click .task-gantt-zoom-2h': 'Zoom2hClick',
        // 'click .task-gantt-zoom-4h': 'Zoom4hClick',
        // 'click .task-gantt-zoom-8h': 'Zoom8hClick',
        //
        // 'click .task-gantt-zoom-days': 'ZoomDaysClick',
        // 'click .task-gantt-zoom-month': 'ZoomMonthClick',
        // 'click .task-gantt-zoom-weeks': 'ZoomWeeksClick',
        // 'click .task-gantt-zoom-quarter': 'ZoomQuarterClick',
        //
        //
        // 'click .task-gantt-today': 'ClickToday',

        'mouseover  .task-gantt-item, .task-gantt-timeline-row'     :'HandleHoverOver',
        'mouseout   .task-gantt-item, .task-gantt-timeline-row'     :'HandleHoverOut'

    },

    custom_events: {

        'sort_item': function (event) {
            this.sort_item(event.target);
        },
     },

    init: function() {
        var self = this;
        this._super.apply(this, arguments);

        this.has_been_loaded = $.Deferred();
        this.chart_id = _.uniqueId();
        this.last_data = null;
        this.scroll_today = 0;
        this.counter = 0;
        this.widgets = [];
        this.options = "all";
        this.gutterClientX  = 0;// how add need info
        this.gutterOffset = this.session.gantt || 400;
        this.gutterOffsetX = 2;
        this.timeline_width = undefined;
        this.timeScale = undefined;
        this.timeWeekPeriod = [];
        this.timeWeekSize = 0;
        this.timePrimary =  [];
        this.timeSecondary =   [];
        this.timeType = undefined;
        this.gantt_timeline_head_widget = undefined;
        this.gantt_timeline_data_widget = [];
        this.pxScaleUTC = undefined;
        this.firstDayScale = undefined;
        this.rows_to_gantt = undefined;
        this.timeScaleUTC = undefined;


        // this.firstDay = undefined;
        // this.lastDay = undefined;

        this.firstDayDate = undefined;
        this.lastDayDate = undefined;


        this.GtimeStartA = [];
        this.GtimeStopA = [];

        this.GtimeStart = undefined;
        this.GtimeStop = undefined;


        //this.BarMovieX = undefined;
        this.BarMovieValue = undefined;
        this.BarClickDiffX = undefined;
        this.BarClickX = undefined;

        this.BarRecord= undefined;

        this.BarClickDown = false;

        this.BarWidth = undefined;

        this.ABarWidth = undefined;
        this.ABarLeft = undefined;
        this.TimeToLeft = false;

        this.ItemsSorted = false;

        this.hint_move_widget = undefined;
        this.tip_move_widget = undefined;

        this.hover_id = undefined;

        this.ScrollToTop = undefined;


        this.Predecessor = undefined;


        this.main_group_id_name = undefined;






    },

    normalizeGutterOffset: function(offset) {
	    var minOffset = 2;
	    var maxOffset = $('.gantt-container').width() - 100;
	    return Math.min(Math.max(offset, minOffset), maxOffset > minOffset ? maxOffset : minOffset);
    },

    willStart: function() {
        var self = this;

        //get options from xml for main group
        self.main_group_id_name = this.fields_view.arch.attrs.main_group_id_name;

        this.$el.addClass(this.fields_view.arch.attrs['class']);
        return self.alive(new Model(this.dataset.model)
            .call('fields_get')).then(function (fields) {
                self.fields = fields;
                self.has_been_loaded.resolve();
            });
    },


        /**
     * Render the buttons according to the GraphView.buttons and
     * add listeners on it.
     * Set this.$buttons with the produced jQuery element
     * @param {jQuery} [$node] a jQuery node where the rendered buttons should be inserted
     * $node may be undefined, in which case the GraphView does nothing
     */
    render_buttons: function ($node) {
        if ($node) {
            var context = {measures: _.pairs(_.omit(this.measures, '__count__'))};
            this.$buttons = $(QWeb.render('APSGanttView.buttons', context));
            this.$buttons.click(this.on_button_click.bind(this));
            // this.$measure_list = this.$buttons.find('.o_graph_measures_list');
            // this.update_measure();
            // this.$buttons.find('button').tooltip();
            // this.$buttons.click(this.on_button_click.bind(this));

            // this.$buttons.find('.o_graph_button[data-mode="' + this.widget.mode + '"]').addClass('active');

            this.$buttons.appendTo($node);
        }
    },

    on_button_click: function (event) {
        var $target = $(event.target);
        if ($target.hasClass('task-gantt-today')) { return this.ClickToday(); }

        if ($target.hasClass('task-gantt-zoom-1h')) { return this.Zoom1hClick(); }
        if ($target.hasClass('task-gantt-zoom-2h')) { return this.Zoom2hClick(); }
        if ($target.hasClass('task-gantt-zoom-4h')) { return this.Zoom4hClick(); }
        if ($target.hasClass('task-gantt-zoom-8h')) { return this.Zoom8hClick(); }
        if ($target.hasClass('task-gantt-zoom-days')) { return this.ZoomDaysClick(); }
        if ($target.hasClass('task-gantt-zoom-month')) { return this.ZoomMonthClick(); }
        if ($target.hasClass('task-gantt-zoom-weeks')) { return this.ZoomWeeksClick(); }
        if ($target.hasClass('task-gantt-zoom-quarter')) { return this.ZoomQuarterClick(); }


        // 'click .task-gantt-zoom-1h': 'Zoom1hClick',
        // 'click .task-gantt-zoom-2h': 'Zoom2hClick',
        // 'click .task-gantt-zoom-4h': 'Zoom4hClick',
        // 'click .task-gantt-zoom-8h': 'Zoom8hClick',
        //
        // 'click .task-gantt-zoom-days': 'ZoomDaysClick',
        // 'click .task-gantt-zoom-month': 'ZoomMonthClick',
        // 'click .task-gantt-zoom-weeks': 'ZoomWeeksClick',
        // 'click .task-gantt-zoom-quarter': 'ZoomQuarterClick',

        // if ($target.hasClass('o_pivot_expand_button')) { return this.expand_all(); }
        // if ($target.parents('.o_pivot_measures_list').length) {
        //     var parent = $target.parent();
        //     var field = parent.data('field');
        //     parent.toggleClass('selected');
        //     event.preventDefault();
        //     event.stopPropagation();
        //     return this.toggle_measure(field);
        // }
        // if ($target.hasClass('o_pivot_download')) {
        //     return this.download_table();
        // }
    },
    get_context: function(){
        if (this.fields_view && this.fields_view.arch.attrs.default_group_by) {
           return {group_by: this.fields_view.arch.attrs.default_group_by.split(',')};
        }
        return {};
    },
    //---1---//
    do_search: function (domains, contexts, group_bys, options) {


        var self = this;

        // Sort allow only if Group by project and domain search by project.
        // Project get from XML = main_group_id_name = "project_id"
        self.ItemsSorted = false;
        if (group_bys.length == 1){

            if (group_bys[0] == self.main_group_id_name){
                 self.ItemsSorted = true;
            }
            if (domains.length > 0){
                if (domains[0][0] != self.main_group_id_name){
                 self.ItemsSorted = false;
                }
            }

            if (domains.length > 1){
                self.ItemsSorted = false;
            }
        }

        if (self.fields_view.arch.attrs.no_group_sort_mode){
            self.ItemsSorted = false;
        }





        self.options = options || 'all';
        self.last_domains = domains;
        self.last_contexts = contexts;
        self.last_group_bys = group_bys;
        self.date_start = null;
        self.date_stop = null;

        var n_group_bys = [];

        // select the group by - we can select group by from attribute where XML if not determinate dafault group
        // for model

        if (this.fields_view.arch.attrs.default_group_by) {
           n_group_bys = this.fields_view.arch.attrs.default_group_by.split(',');
        }

        if (group_bys.length) {
            n_group_bys = group_bys;
        }


        var getFields = GanttToolField.getFields(self, group_bys);
        self.model_fields = getFields["model_fields"];
        self.model_fields_dict = getFields["model_fields_dict"];



        // Options wise view loading [Year, Month, Week]

        if (self.options == 'all') {
            self.domains = domains;
        }

        return $.when(this.has_been_loaded).then(function() {
            return self.dataset.read_slice(self.model_fields, {
                domain: domains,
                context: contexts
            }).then(function(data) {
                if (data.length) {

                    return self.on_data_loaded_dummy(data, n_group_bys);

                } else {
                    return alert('No data found...');
                }
            });
        });


    },


    on_data_loaded_dummy: function(tasks, group_bys) {
        var self = this;

        return self.on_data_loaded_predecessor(tasks, group_bys);

        //var ids = _.pluck(tasks, "id");
        // if (self.ItemsSorted) {
        //
        //
        //     var split_groups = function(tasks, group_bys) {
        //         if (group_bys.length === 0){
        //             return tasks;
        //         }
        //         var sp_groups = [];
        //         _.each(tasks, function(task) {
        //             var group_name = task[_.first(group_bys)];
        //             var group = _.find(sp_groups, function(group) { return _.isEqual(group.id, group_name[0]); });
        //             if (group === undefined) {
        //                 try {
        //                     group = {id:group_name[0]};
        //                 } catch (err) {
        //
        //                     self.ItemsSorted = false;
        //                     return;
        //                 }
        //                 sp_groups.push(group);
        //             }
        //         });
        //                 return sp_groups;
        //     };
        //
        //
        //
        //     var groups = split_groups(tasks, ["subtask_project_id"]);
        //
        //
        //     var test = false;
        //
        //     var p_model = new Model(this.dataset.model);
        //
        //     p_model.call('childs_get', ["subtask_project_id", groups, self.model_fields ]).then(function(result) {
        //         test = result;
        //         return self.on_data_loaded_predecessor(tasks, group_bys);
        //
        //     });
        //
        //
        // }
        // else{
        //
        //     return self.on_data_loaded_predecessor(tasks, group_bys);
        // }

    },




    //Fist Entry poin load predecessor after. get atributes from XML
    on_data_loaded_predecessor: function(tasks, group_bys) {
        var self = this;
        var ids = _.pluck(tasks, "id");

        var predecessor_model = self.fields_view.arch.attrs.predecessor_model;
        var predecessor_task_id = self.fields_view.arch.attrs.predecessor_task_id;
        var predecessor_parent_task_id = self.fields_view.arch.attrs.predecessor_parent_task_id;
        var predecessor_type = self.fields_view.arch.attrs.predecessor_type;

        if (predecessor_model) {

            var dataset = new data.DataSetSearch(self, predecessor_model, session.context, [[predecessor_task_id, 'in', _.uniq(ids)]]);

            dataset.read_slice([predecessor_task_id, predecessor_parent_task_id, predecessor_type]).then(function (result) {
                return result;
            }).then(function (result) {
                self.Predecessor = result;
                return self.on_data_loaded_ghost(tasks, group_bys);
            })
        }
        else{
            return self.on_data_loaded_ghost(tasks, group_bys);
        }

    },

        //Fist Entry poin load predecessor after. get atributes from XML
    on_data_loaded_ghost: function(tasks, group_bys) {
        var self = this;
        var ids = _.pluck(tasks, "id");

        var ghost_id = self.fields_view.arch.attrs.ghost_id;
        var ghost_model = self.fields_view.arch.attrs.ghost_model;
        var ghost_name = self.fields_view.arch.attrs.ghost_name;
        var ghost_date_start = self.fields_view.arch.attrs.ghost_date_start;
        var ghost_date_end = self.fields_view.arch.attrs.ghost_date_end;
        var ghost_durations = self.fields_view.arch.attrs.ghost_durations;

        if (ghost_model) {

            var dataset = new data.DataSetSearch(self, ghost_model, session.context, [[ghost_id, 'in', _.uniq(ids)]]);

            dataset.read_slice([ghost_id ,ghost_name, ghost_date_start, ghost_date_end, ghost_durations]).then(function (result) {
                return result;

            }).then(function (result) {
                self.Ghost = result;
                self.Ghost_Data = GanttTimeLineGhost.get_data_ghosts(self);

                return self.on_data_loaded_barfirst(tasks, group_bys);
            })
        }
        else{
            return self.on_data_loaded_barfirst(tasks, group_bys);
        }

    },

    on_data_loaded_barfirst: function(tasks, group_bys) {

        var self = this;

        if (self.ItemsSorted) {

            var barfirst_field = "project_id";


            var barfirst_field_ids = _.pluck(tasks, "project_id");

            var ids = _.pluck(barfirst_field_ids, "0");

            var barfirst_model = "project.project";
            var barfirst_name = "name";
            var barfirst_date_start = "date_start";
            var barfirst_date_end = "date_end";

            var dataset = new data.DataSetSearch(self, barfirst_model, session.context, [['id', 'in', _.uniq(ids)]]);

            dataset.read_slice(['id', barfirst_name, barfirst_date_start, barfirst_date_end]).then(function (result) {
                return result;

            }).then(function (result) {
                self.BarFirst = result;
                self.BarFirst_Data = GanttTimeLineFirst.get_data_barfirst(self);

                return self.on_data_loaded_name_get(tasks, group_bys);
            })
        }
        else{
            return self.on_data_loaded_name_get(tasks, group_bys);
        }

    },



    //Get name get from model form name field
    on_data_loaded_name_get: function(tasks, group_bys) {
        var self = this;
        var ids = _.pluck(tasks, "id");


        self.dataset.name_get(ids).then(function(names) {

            var ntasks = _.map(tasks, function(task) {
                    return _.extend({__name: _.detect(names, function(name) { return name[0] == task.id; })[1]}, task);
            });

            return self.gantt_render(ntasks, group_bys);
        });

    },



    reload: function () {
        var self = this;

        return self.do_search(self.last_domains, self.last_contexts, self.last_group_bys, self.options);

    },


    gantt_render: function(tasks, group_bys){
        var self = this;

        //Group Rows
        var groupRows = GanttToolField.groupRows(tasks, group_bys, self);

        //Get all tasks with group
        self.projects = groupRows["projects"];

        //Get Max Min date for data
        self.GtimeStopA = self.GtimeStopA.concat(groupRows["timestop"]);
        self.GtimeStartA = self.GtimeStartA.concat(groupRows["timestart"]);

        //Calc Min - Max
        self.GtimeStart = Math.min.apply(null, self.GtimeStartA); // MAX date in date range
        self.GtimeStop = Math.max.apply(null, self.GtimeStopA); // Min date in date range
        //Clean
        self.GtimeStartA = [];
        self.GtimeStopA = [];


        //set time scale type if is undefined
        if ( self.timeType === undefined ) {
            self.timeType = 'month_day';
        }

        //Gantt Conteriner Render.
        self.$el.html(QWeb.render('GanttContainerView.main', {
            'title': "My Table",
            'widget': self,
            'display_name': this.display_name,
            'gutterOffset' : this.gutterOffset,

        }));

        //Sorted and grouped to flat list
        self.rows_to_gantt = GanttToolField.flatRows(self.projects);

        //Gantt Data Widget Render
        _.map(self.rows_to_gantt, function(record){

            var row = new GanttListItem(self, record, self.ItemsSorted);
            row.appendTo(self.$('.task-gantt-items'));
            self.widgets.push(row);

            }
        );

                //Gantt Data Widget Render
        _.map(self.rows_to_gantt, function(record){

            var row = new GanttItemSorted.GanttListSortingItem(self, record);
            row.appendTo(self.$('.task-sorting-items'));
            self.widgets.push(row);

            }
        );



        // Start - End month
        self.firstDayDate = moment(self.GtimeStart).clone().startOf('month'); //Start month
        self.lastDayDate = moment(self.GtimeStop).clone().endOf('month'); //End month
        self.timeScaleUTC = self.lastDayDate.valueOf() - self.firstDayDate.valueOf(); // raznica vremeni
        self.firstDayScale = self.firstDayDate.valueOf();

        //Get Zoom Event from time scale type

        if (self.timeType === 'month_day'){
            self.ZoomDaysClick();
        }

        if (self.timeType === 'day_1hour'){
            self.Zoom1hClick();
        }
        if (self.timeType === 'day_2hour'){
            self.Zoom2hClick();
        }
        if (self.timeType === 'day_4hour'){
            self.Zoom4hClick();
        }
        if (self.timeType === 'day_8hour'){
            self.Zoom8hClick();
        }

        if (self.timeType === 'year_month'){

             self.ZoomMonthClick();
        }

        if (self.timeType === 'month_week'){

             self.ZoomWeeksClick();
        }
        if (self.timeType === 'quarter'){

             self.ZoomQuarterClick();
        }


        //Sorted Item if sorted allow
        GanttItemSorted.sorted(self, this.ItemsSorted);

        //Update

        //Get Getter offset from session
        $('.task-gantt-list').width(self.session.gantt || self.gutterOffset);

        //Hover selected rows after refresh page
        var rowdata = '#task-gantt-timeline-row-'+self.hover_id;
        var rowitem = '#task-gantt-item-'+self.hover_id;

        $(rowdata).addClass("task-gantt-timeline-row-hover");
        $(rowitem).addClass("task-gantt-item-hover");


        // Goto Vertial and Horizontal Scroll
        if (self.TimeToLeft) {
            var task_left = self.TimeToLeft;
            $('.task-gantt-timeline').animate({
                scrollLeft: task_left
                }, 0, function() {
            // Animation complete.
            });
            $('.timeline-gantt-head').animate({
                scrollLeft: task_left
                }, 0, function() {
            // Animation complete.
            });


            self.gantt_timeline_scroll_widget.scrollOffset(task_left);


        }

        if (self.ScrollToTop) {
           var panel_top = self.ScrollToTop;
            $('.task-gantt').animate({
                scrollTop: panel_top
                }, 0, function() {
            // Animation complete.
          });
        }







    }, //end update


    AddTimeLineArrow: function( timeline_width ) {

        var self = this;
        if (self.gantt_timeline_arrow_widget){
            this.gantt_timeline_arrow_widget.destroy();
            self.gantt_timeline_arrow_widget = [];
        }

        this.gantt_timeline_arrow_widget = new GanttTimeLineArrow(self, timeline_width );
        this.gantt_timeline_arrow_widget.appendTo(self.$('.task-gantt-timeline-inner'));

    },


    AddTimeLineHead: function(timeScale, time_type, time_month, time_day ) {

        var self = this;
        if (this.gantt_timeline_head_widget){
            this.gantt_timeline_head_widget.destroy();
        }

        this.gantt_timeline_head_widget = new GanttTimeLineHead(self, timeScale, time_type, time_month, time_day  );
        this.gantt_timeline_head_widget.appendTo(self.$('.task-gantt-timeline-inner'));


        if (this.gantt_timeline_header_widget){
            this.gantt_timeline_header_widget.destroy();
            this.gantt_timeline_header_widget = [];
        }

        this.gantt_timeline_header_widget = new GanttTimeLineHeader(self, timeScale, time_type, time_month, time_day  );

        // var ctrl_panel = $('.o_control_panel');
        var ctrl_panel = $('.timeline-gantt');
        this.gantt_timeline_header_widget.appendTo(ctrl_panel);




        if (this.gantt_timeline_scroll_widget){
            this.gantt_timeline_scroll_widget.destroy();
            this.gantt_timeline_scroll_widget = [];
        }


        this.gantt_timeline_scroll_widget = new GanttTimeLineScroll(self, timeScale, time_type, time_month, time_day  );

        // var ctrl_panel = $('.o_control_panel');
        var scroll_panel = $('.timeline-gantt-scroll');
        this.gantt_timeline_scroll_widget.appendTo(scroll_panel);



        // Goto Horizontal Scroll
        if (this.TimeToLeft) {
            var task_left = this.TimeToLeft;
            $('.task-gantt-timeline').animate({
                scrollLeft: task_left
                }, 0, function() {
            // Animation complete.
            });
            $('.timeline-gantt-head').animate({
                scrollLeft: task_left
                }, 0, function() {
            // Animation complete.
            });

            self.gantt_timeline_scroll_widget.scrollOffset(task_left);


        }

    },


     AddTimeLineData: function(timeScale, time_type, rows_to_gantt ) {

        var self = this;
        if (this.gantt_timeline_data_widget.length > 0){
            this.gantt_timeline_data_widget = [];
           //  _.each(this.gantt_timeline_data_widget, function(data_widget) {
           //      data_widget.destroy();
           //  })
        }
        _.map(rows_to_gantt, function (record) {

             var gantt_time_line_data = new GanttTimeLineData(self, timeScale, time_type, record);

             gantt_time_line_data.appendTo(self.$('.task-gantt-timeline-data'));
             self.gantt_timeline_data_widget.push(gantt_time_line_data);
        });

     },

    AddTimeLineGhost: function() {

        var self = this;
        if (self.gantt_timeline_ghost_widget){
            this.gantt_timeline_ghost_widget.destroy();
            self.gantt_timeline_ghost_widget = [];
        }

        this.gantt_timeline_ghost_widget = new GanttTimeLineGhost.GhostWidget(self);
        this.gantt_timeline_ghost_widget.appendTo(self.$('.task-gantt-timeline-data'));

    },

    AddTimeLineSummary: function() {

        var self = this;
        if (self.gantt_timeline_summary_widget){
            this.gantt_timeline_summary_widget.destroy();
            self.gantt_timeline_summary_widget = [];
        }

        this.gantt_timeline_summary_widget = new GanttTimeLineSummary.SummaryWidget(self);
        this.gantt_timeline_summary_widget.appendTo(self.$('.task-gantt-timeline-data'));

    },

    AddTimeLineFirst: function() {

        var self = this;
        if (self.gantt_timeline_first_widget){
            this.gantt_timeline_first_widget.destroy();
            self.gantt_timeline_first_widget = [];
        }

        this.gantt_timeline_first_widget = new GanttTimeLineFirst.BarFirstWidget(self);
        this.gantt_timeline_first_widget.appendTo(self.$('.task-gantt-timeline-data'));

    },


//Zoom Out - Zoom In



    Zoom1hClick: function() {
        this.ZoomHoursClick(1, 'day_1hour' );
        // this.timeType = 'day_1hour';
    },
    Zoom2hClick: function() {
        this.ZoomHoursClick(2, 'day_2hour');
        // this.timeType = 'day_2hour';
    },
    Zoom4hClick: function() {
        this.ZoomHoursClick(4, 'day_4hour');
        // this.timeType = 'day_4hour';
    },
    Zoom8hClick: function() {
        this.ZoomHoursClick(8, 'day_8hour');
        // this.timeType = 'day_8hour';
    },



    ZoomHoursClick: function(div_hour, timeType) {

                this.firstDayDate = moment(this.GtimeStart).clone().startOf('month'); //Start month
        this.lastDayDate = moment(this.GtimeStop).clone().endOf('month'); //End
        this.timeScaleUTC = this.lastDayDate.valueOf() - this.firstDayDate.valueOf(); // raznica vremeni
        this.firstDayScale = this.firstDayDate.valueOf();

        var iter = moment(this.firstDayDate).twix(this.lastDayDate).iterate(div_hour, 'hours');

        var hour2Range=[];
        while(iter.hasNext()){

             hour2Range.push(iter.next().toDate())

        }


        var daysGroup = _(hour2Range).groupBy(function (day) {
             return moment(day).format("YYYY MM DD");

        });

        this.timeType = timeType;
        this.timeScale = 40; //px

        this.timeline_width = this.timeScale*hour2Range.length; // min otrzok 60 - eto 4 4asa. v sutkah 6 otrezkov
        this.pxScaleUTC = Math.round(this.timeScaleUTC / this.timeline_width); // skolko vremeni v odnom px



        this.AddTimeLineHead(this.timeScale, this.timeType, daysGroup, false );
        this.AddTimeLineData(this.timeScale, this.timeType, this.rows_to_gantt);

        this.AddTimeLineArrow(this.timeline_width);

        this.AddTimeLineGhost();

        this.AddTimeLineSummary();
        this.AddTimeLineFirst();



    },

    ZoomDaysClick: function() {

                this.firstDayDate = moment(this.GtimeStart).clone().startOf('month'); //Start month
        this.lastDayDate = moment(this.GtimeStop).clone().endOf('month'); //End
        this.timeScaleUTC = this.lastDayDate.valueOf() - this.firstDayDate.valueOf(); // raznica vremeni
        this.firstDayScale = this.firstDayDate.valueOf();

        var currentLocaleData = moment.localeData();

        //Get Days Range
        var iter = moment(this.firstDayDate).twix(this.lastDayDate).iterate("days");

        var dayRange=[];
        while(iter.hasNext()){
            dayRange.push(iter.next().toDate())
        }

        //Get Year - Month range
        var iter_first = moment(this.firstDayDate).twix(this.lastDayDate).iterate("month");

        var monthRange=[];
        while(iter_first.hasNext()){

            var mt_month = iter_first.next();
            var month = [];

            month['year'] =  mt_month.year();
            month['month'] =  currentLocaleData.months(mt_month);
            month['days'] =  mt_month.daysInMonth();

            monthRange.push(month)
        }

        this.timeScale = 24; //px
        this.timeType = 'month_day';
        this.timeline_width = this.timeScale*dayRange.length;
        this.pxScaleUTC = Math.round(this.timeScaleUTC / this.timeline_width); // skolko vremeni v odnom px



        this.AddTimeLineHead(this.timeScale, this.timeType, monthRange, dayRange );
        this.AddTimeLineData(this.timeScale, this.timeType, this.rows_to_gantt);

        this.AddTimeLineArrow(this.timeline_width);
        this.AddTimeLineGhost();

        this.AddTimeLineSummary();
        this.AddTimeLineFirst();

    },

    ZoomMonthClick: function() {

        this.firstDayDate = moment(this.GtimeStart).clone().startOf('month'); //Start month
        this.lastDayDate = moment(this.GtimeStop).clone().endOf('month'); //End
        this.timeScaleUTC = this.lastDayDate.valueOf() - this.firstDayDate.valueOf(); // raznica vremeni
        this.firstDayScale = this.firstDayDate.valueOf();

        var iter = moment(this.firstDayDate).twix(this.lastDayDate).iterate('month');

        var month2Range=[];
        while(iter.hasNext()){

             month2Range.push(iter.next().toDate())

        }

        var monthGroup = _(month2Range).groupBy(function (month) {
             return moment(month).format("YYYY");

        });


        this.timeScale = 30 ;//px
        this.timeType = 'year_month';

        this.timeline_width = this.timeScale*month2Range.length; // min otrzok 60 - eto 4 4asa. v sutkah 6 otrezkov
        this.pxScaleUTC = Math.round(this.timeScaleUTC / this.timeline_width); // skolko vremeni v odnom px

        this.AddTimeLineHead(this.timeScale, this.timeType, monthGroup, false );
        this.AddTimeLineData(this.timeScale, this.timeType, this.rows_to_gantt);

        this.AddTimeLineArrow(this.timeline_width);
        this.AddTimeLineGhost();

        this.AddTimeLineSummary();
        this.AddTimeLineFirst();

    },


    ZoomWeeksClick: function() {

        this.firstDayDate = moment(this.GtimeStart).clone().startOf('isoWeek'); //Start month
        this.lastDayDate = moment(this.GtimeStop).clone().endOf('isoWeek'); //End
        this.timeScaleUTC = this.lastDayDate.valueOf() - this.firstDayDate.valueOf(); // raznica vremeni
        this.firstDayScale = this.firstDayDate.valueOf();

        var iter = moment(this.firstDayDate).twix(this.lastDayDate).iterate('Week');

        var week2Range=[];
        while(iter.hasNext()){

             week2Range.push(iter.next().toDate())

        }

        var weeksGroup = _(week2Range).groupBy(function (week) {
             return moment(week).format("YYYY");

        });


        this.timeScale = 30 ;//px
        this.timeType = 'month_week';

        this.timeline_width = this.timeScale*week2Range.length; // min otrzok 60 - eto 4 4asa. v sutkah 6 otrezkov
        this.pxScaleUTC = Math.round(this.timeScaleUTC / this.timeline_width); // skolko vremeni v odnom px


        this.AddTimeLineHead(this.timeScale, this.timeType, weeksGroup, false );
        this.AddTimeLineData(this.timeScale, this.timeType, this.rows_to_gantt);

        this.AddTimeLineArrow(this.timeline_width);
        this.AddTimeLineGhost();
        this.AddTimeLineSummary();
        this.AddTimeLineFirst();


    },


    ZoomQuarterClick: function() {


        this.firstDayDate = moment(this.GtimeStart).clone().startOf('Quarter'); //Start month
        this.lastDayDate = moment(this.GtimeStop).clone().endOf('Quarter'); //End
        this.timeScaleUTC = this.lastDayDate.valueOf() - this.firstDayDate.valueOf(); // raznica vremeni
        this.firstDayScale = this.firstDayDate.valueOf();


        var iter = moment(this.firstDayDate).twix(this.lastDayDate).iterate('Quarter');

        var quarter2Range=[];
        while(iter.hasNext()){

             quarter2Range.push(iter.next().toDate())

        }

        var quarterGroup = _(quarter2Range).groupBy(function (quarter) {
             return moment(quarter).format("YYYY");

        });


        this.timeScale = 80 ;//px
        this.timeType = 'quarter';

        this.timeline_width = this.timeScale*quarter2Range.length; // min otrzok 60 - eto 4 4asa. v sutkah 6 otrezkov
        this.pxScaleUTC = Math.round(this.timeScaleUTC / this.timeline_width); // skolko vremeni v odnom px


        this.AddTimeLineHead(this.timeScale, this.timeType, quarterGroup, false );
        this.AddTimeLineData(this.timeScale, this.timeType, this.rows_to_gantt);

        this.AddTimeLineArrow(this.timeline_width);
        this.AddTimeLineGhost();
        this.AddTimeLineSummary();
        this.AddTimeLineFirst();


    },



//Gutter Movie

    GutterMouseDown: function(event){

        this.$el.delegate('.task-gantt', 'mouseup', this.proxy('GutterMouseUp'));
        this.$el.delegate('.task-gantt', 'mousemove', this.proxy('GutterMouseMove'));
        this.gutterClientX = event.clientX;
    },


    GutterMouseUp: function(event){

        this.$el.undelegate('.task-gantt', 'mouseup');
        this.$el.undelegate('.task-gantt', 'mousemove');
    },

    GutterMouseMove: function(event){

        var parentOffset = $('.task-gantt-gutter').parent().offset();
        var pxc = this.gutterOffsetX + (event.clientX - parentOffset.left);

        $('.task-gantt-list').width(pxc);
        $('.timeline-gantt-items').width(pxc+20);


        this.session.gantt = pxc;
        this.gutterOffsetSession = pxc;
    },


//Today Focus of Gantt Line Focus
    ClickToday: function (event) {

        var today = new Date();

        var toscale = this.TimeToScale(today.getTime());

        this.TimeToLeft = toscale;
        this.Focus_Gantt(toscale);

    },

    // Any can focus on BAR
    Focus_Gantt: function(task_start){



        $('.timeline-gantt-head').animate( { scrollLeft: task_start-500 }, 1000);
        $('.task-gantt-timeline').animate( { scrollLeft: task_start-500 }, 1000);

        this.gantt_timeline_scroll_widget.scrollOffset(task_start-500);


        // var scale_width = $('.timeline-gantt-scroll-scale').width()-50;
        //
        // var x1 = $('.task-gantt-timeline').width();
        // var x2 = $('.task-gantt-timeline-data').width();
        // var  scroll_width = x2 - x1;
        //
        // var scale = scroll_width/(scale_width);
        //
        // var offset_left = (task_start-500) / scale;
        //
        // if (offset_left > scale_width){
        //
        //     offset_left = scale_width
        // }
        //
        // if (offset_left < 0){
        //
        //     offset_left = 0
        // }
        //
        //
        // $(".timeline-gantt-scroll-slider").offset({ left: offset_left  });



    },

    TimeToScale: function(time){

       if (time){

        return Math.round((time-this.firstDayScale) / this.pxScaleUTC);
    }

    },



// HandleHover

    HandleHoverOver: function(ev) {

        if (ev.target.allowRowHover)
        {

            var rowsort = '#task-gantt-item-sorting-'+ev.target['data-id'];
            var rowdata = '#task-gantt-timeline-row-'+ev.target['data-id'];
            var rowitem = '#task-gantt-item-'+ev.target['data-id'];

            $(rowsort).addClass("task-gantt-sorting-item-hover");
            $(rowdata).addClass("task-gantt-timeline-row-hover");
            $(rowitem).addClass("task-gantt-item-hover");

        }

    },


    HandleHoverOut: function(ev) {

        var rowsort = '#task-gantt-item-sorting-'+ev.target['data-id'];
        var rowdata = '#task-gantt-timeline-row-'+ev.target['data-id'];
        var rowitem = '#task-gantt-item-'+ev.target['data-id'];

        $(rowsort).removeClass("task-gantt-sorting-item-hover");
        $(rowdata).removeClass("task-gantt-timeline-row-hover");
        $(rowitem).removeClass("task-gantt-item-hover");

        // console.debug(ev);

    }


});

core.view_registry.add('ganttaps', GanttContainer);

return GanttContainer;
});
