robo.define('robo.Calendar', function (require) {
"use strict";
    
var core = require('web.core');
var time = require('web.time');
var utils = require('web.utils');
var CalendarView = require('web_calendar.CalendarView');
    
var _t = core._t;

function get_fc_defaultOptions() {
    var dateFormat = time.strftime_to_moment_format(_t.database.parameters.date_format);

    // moment.js converts '%p' to 'A' for 'AM/PM'
    // But FullCalendar v1.6.4 supports 'TT' format for 'AM/PM' but not 'A'
    // NB: should be removed when fullcalendar is updated to 2.0 because it would
    // be supported. See the following link
    // http://fullcalendar.io/wiki/Upgrading-to-v2/
    var timeFormat = time.strftime_to_moment_format(_t.database.parameters.time_format).replace('A', 'TT');

    // adapt format for fullcalendar v1.
    // see http://fullcalendar.io/docs1/utilities/formatDate/
    var conversions = [['YYYY', 'yyyy'], ['YY', 'y'], ['DDDD', 'dddd'], ['DD', 'dd']];
    _.each(conversions, function(conv) {
        dateFormat = dateFormat.replace(conv[0], conv[1]);
    });

    // If 'H' is contained in timeFormat display '10:00'
    // Else display '10 AM'.
    // See : http://fullcalendar.io/docs1/utilities/formatDate/
    var hourFormat = function(timeFormat){
        if (/H/.test(timeFormat))
            return 'HH:mm';
        return 'hh TT';
    };

    return {
        weekNumberTitle: _t("S"),
        allDayText: _t("Visą dieną"),
        monthNames: moment.months(),
        monthNamesShort: moment.monthsShort(),
        dayNames: moment.weekdays(),
        dayNamesShort: moment.weekdaysShort(),
        firstDay: moment._locale._week.dow,
        weekNumberCalculation: function(date) {
            return moment(date).week();
        },
        axisFormat: hourFormat(timeFormat),
        // Correct timeformat for agendaWeek and agendaDay
        // http://fullcalendar.io/docs1/text/timeFormat/
        timeFormat: timeFormat + ' {- ' + timeFormat + '}',
        weekNumbers: true,
        titleFormat: {
            month: 'MMMM yyyy',
            week: "s",
            day: dateFormat,
        },
        columnFormat: {
            month: 'ddd',
            week: 'ddd ' + dateFormat,
            day: 'dddd ' + dateFormat,
        },
        weekMode : 'liquid',
        snapMinutes: 15,
    };
}

function is_virtual_id(id) {
    return typeof id === "string" && id.indexOf('-') >= 0;
}

function isNullOrUndef(value) {
    return _.isUndefined(value) || _.isNull(value);
}
    
var RoboCalendar = CalendarView.extend({

    init: function () {
        this._super.apply(this, arguments);
        this.color_map = {};
        this.range_start = null;
        this.range_stop = null;
        this.selected_filters = [];
        this.info_fields = [];

        this.title = (this.options.action)? this.options.action.name : '';

        this.shown = $.Deferred();
        this.current_start = null;
        this.current_end = null;
        this.previous_ids = [];

        var attrs = this.fields_view.arch.attrs;
        if (!attrs.date_start) {
            throw new Error(_t("Calendar view has not defined 'date_start' attribute."));
        }
        this.fields = this.fields_view.fields;
        this.name = this.fields_view.name || attrs.string;
        this.mode = attrs.mode;                 // one of month, week or day
        this.date_start = attrs.date_start;     // Field name of starting date field
        this.date_delay = attrs.date_delay;     // duration
        this.date_stop = attrs.date_stop;
        this.all_day = attrs.all_day;
        this.how_display_event = '';
        this.attendee_people = attrs.attendee;

        // Check whether the date field is editable (i.e. if the events can be dragged and dropped)
        this.editable = !this.options.read_only_mode && !this.fields[this.date_start].readonly;

        //if quick_add = False, we don't allow quick_add
        //if quick_add = not specified in view, we use the default quick_create_instance
        //if quick_add = is NOT False and IS specified in view, we this one for quick_create_instance'

        this.quick_add_pop = (isNullOrUndef(attrs.quick_add) || utils.toBoolElse(attrs.quick_add, true));
        // The display format which will be used to display the event where fields are between "[" and "]"
        if (!isNullOrUndef(attrs.display)) {
            this.how_display_event = attrs.display; // String with [FIELD]
        }

        // If this field is set ot true, we don't open the event in form view, but in a popup with the view_id passed by this parameter
        if (isNullOrUndef(attrs.event_open_popup) || !utils.toBoolElse(attrs.event_open_popup, true)) {
            this.open_popup_action = false;
        } else {
            this.open_popup_action = attrs.event_open_popup;
        }
        // If this field is set to true, we will use the calendar_friends model as filter and not the color field.
        this.useContacts = !isNullOrUndef(attrs.use_contacts) && _.str.toBool(attrs.use_contacts);

        // If this field is set ot true, we don't add itself as an attendee when we use attendee_people to add each attendee icon on an event
        // The color is the color of the attendee, so don't need to show again that it will be present
        this.colorIsAttendee = !(isNullOrUndef(attrs.color_is_attendee) || !utils.toBoolElse(attrs.color_is_attendee, true));

        // if we have not sidebar, (eg: Dashboard), we don't use the filter "coworkers"
        if (isNullOrUndef(this.options.sidebar)) {
            this.useContacts = false;
            this.colorIsAttendee = false;
            this.attendee_people = undefined;
        }

        /*
                Will be more logic to do it in futur, but see below to stay Retro-compatible

                if (isNull(attrs.avatar_model)) {
                    this.avatar_model = 'res.partner';
                }
                else {
                    if (attrs.avatar_model == 'False') {
                        this.avatar_model = null;
                    }
                    else {
                        this.avatar_model = attrs.avatar_model;
                    }
                }
        */
        if (isNullOrUndef(attrs.avatar_model)) {
            this.avatar_model = null;
        } else {
            this.avatar_model = attrs.avatar_model;
        }

        if (isNullOrUndef(attrs.avatar_title)) {
            this.avatar_title = this.avatar_model;
        } else {
            this.avatar_title = attrs.avatar_title;
        }

        if (isNullOrUndef(attrs.avatar_filter)) {
            this.avatar_filter = this.avatar_model;
        } else {
            this.avatar_filter = attrs.avatar_filter;
        }

        this.color_field = attrs.color;

        if (this.color_field && this.selected_filters.length === 0) {
            var default_filter;
            if ((default_filter = this.dataset.context['calendar_default_' + this.color_field])) {
                this.selected_filters.push(default_filter + '');
            }
        }

        for (var fld = 0; fld < this.fields_view.arch.children.length; fld++) {
            this.info_fields.push(this.fields_view.arch.children[fld].attrs.name);
        }
    },

    get_fc_init_options: function () {
        //Documentation here : http://arshaw.com/fullcalendar/docs/
        var self = this;
        return $.extend({}, get_fc_defaultOptions(), {
            defaultView: (this.mode == "month")? "month" : ((this.mode == "week")? "agendaWeek" : ((this.mode == "day")? "agendaDay" : "agendaWeek")),
            header: false,
            selectable: !this.options.read_only_mode && this.create_right,
            selectHelper: true,
            editable: this.editable,
            droppable: true,

            // callbacks
            viewRender: function(view) {
                var mode = (view.name == "month")? "month" : ((view.name == "agendaWeek") ? "week" : "day");
                if(self.$buttons !== undefined) {
                    self.$buttons.find('.active').removeClass('active');
                    self.$buttons.find('.o_calendar_button_' + mode).addClass('active');
                }

                var title = self.title + ' (' + ((mode === "week")? _t("Savaitė ") : "") + view.title + ")";
                self.set({'title': title});

                self.$calendar.fullCalendar('option', 'height', Math.max(290, parseInt(self.$('.o_calendar_view').height())));

                setTimeout(function() {
                    var $fc_view = self.$calendar.find('.fc-view');
                    var width = $fc_view.find('> table').width();
                    $fc_view.find('> div').css('width', (width > $fc_view.width())? width : '100%'); // 100% = fullCalendar default
                }, 0);
            },
            windowResize: function() {
                self.$calendar.fullCalendar('render');
            },
            eventDrop: function (event, _day_delta, _minute_delta, _all_day, _revertFunc) {
                var data = self.get_event_data(event);
                self.proxy('update_record')(event._id, data); // we don't revert the event, but update it.
            },
            eventResize: function (event, _day_delta, _minute_delta, _revertFunc) {
                var data = self.get_event_data(event);
                self.proxy('update_record')(event._id, data);
            },
            eventRender: function (event, element, view) {
                element.find('.fc-event-title').html(event.title);
            },
            eventAfterRender: function (event, element, view) {
                if ((view.name !== 'month') && (((event.end-event.start)/60000)<=30)) {
                    //if duration is too small, we see the html code of img
                    var current_title = $(element.find('.fc-event-time')).text();
                    var new_title = current_title.substr(0,current_title.indexOf("<img")>0?current_title.indexOf("<img"):current_title.length);
                    element.find('.fc-event-time').html(new_title);
                }
            },
            eventClick: function (event) { self.open_event(event._id,event.title); },
            select: function (start_date, end_date, all_day, _js_event, _view) {
            },

            unselectAuto: false,
        });
    },

    event_data_transform: function(evt) {
        var r = this._super.apply(this, arguments);
        //ROBO: somehow hides the time info in calendar
        r.allDay = true;
        return r;
    },

});
core.view_registry.add('calendar_robo', RoboCalendar);
return RoboCalendar;
});

