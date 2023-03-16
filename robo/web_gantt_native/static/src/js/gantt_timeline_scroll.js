robo.define('web_gantt_native.TimeLineScroll', function (require) {
"use strict";

var config = require('web.config');
var core = require('web.core');
var Dialog = require('web.Dialog');
var form_common = require('web.form_common');
var Widget = require('web.Widget');
var time = require('web.time');

var _lt = core._lt;
var _t = core._t;
var QWeb = core.qweb;


var GanttTimeLineScroll = Widget.extend({
    template: "TimelineGantt.scroll",

    init: function(parent, timeScale, timeType, first_scale, second_scale) {
        this._super(parent);

        this.timeScale = timeScale;
        this.timeType = timeType;

        this.first_scale = first_scale;
        this.second_scale = second_scale;

        this.TODAY = moment();

       // this.record_id = this.record['id']

    },


    scrollOffset: function (gantt_data_offset){


                var scale_width = $('.timeline-gantt-scroll-scale').width()-50;

                var x1 = $('.task-gantt-timeline').width();
                var x2 = $('.task-gantt-timeline-data').width();
                var  scroll_width = x2 - x1;

                var scale = scroll_width/(scale_width);

                var offset_left = (gantt_data_offset) / scale;

                if (offset_left > scale_width){

                    offset_left = scale_width
                }

                if (offset_left < 0){

                    offset_left = 0
                }


                $(".timeline-gantt-scroll-slider").offset({ left: offset_left  });




    },


    updateCounterStatus: function ($event_counter, scale_width ,scroll_width) {
      // first update the status visually...
      // if ( !$event_counter.hasClass( "ui-state-hover" ) ) {
      //   $event_counter.addClass( "ui-state-hover" )
      //     .siblings().removeClass( "ui-state-hover" );
      // }

        var self = this.__parentedParent;

        var offset = $event_counter.offset();
        var offset_left = offset.left;

        var left_menu_offset_left = $('.o_main_content').offset().left;

        var scale = scroll_width/(scale_width-50);
        var scale_x = (offset_left - left_menu_offset_left) * scale;


        $('.timeline-gantt-head').animate( { scrollLeft: scale_x }, 0);
        $('.task-gantt-timeline').animate( { scrollLeft: scale_x }, 0);


        var test = 45;

        // var toscale = self.TimeToScale(event.target.record.task_start.getTime());
        //
        // self.TimeToLeft = toscale;
        // self.Focus_Gantt(toscale);



    },



    start: function(){

        var self = this;
        var el = self.$el;

        // $(window).resize(function () {
        //
        //     var size_scale = $('.timeline-gantt-scroll-scale').width();
        //     var test = $(document);
        //     var sdf = 34;
        // });

        var gutterOffset = self.__parentedParent.gutterOffsetSession || self.__parentedParent.gutterOffset;

            //         <!--<div class="timeline-gantt-items">-->
            //     <!--<div class="timeline-gantt-gutter"></div>-->
            // <!--</div>-->
            //
            // <!--<div class="timeline-gantt-head"></div>-->

        // var el_gantt_items = el.find('.timeline-gantt-items');
        //
        // el_gantt_items.css("width", gutterOffset+20);


        // 'gutterOffset' : this.gutterOffset,

         // <div class="timeline-gantt-items">

        // this.$el.append('<div class="timeline-gantt-h-scroll">OK</div>');


        // var el_scale_primary = el.find('.timeline-gantt-scroll-scale');
        // var el_scale_secondary = el.find('.timeline-gantt-scale-secondary');


       // if (this.timeType == 'month_day')
       // {

            var div_cell = $('<div class="timeline-gantt-scroll-slider"></div>');


    //              $( "#draggable" ).draggable({
    //   start: function() {
    //     counts[ 0 ]++;
    //     updateCounterStatus( $start_counter, counts[ 0 ] );
    //   },
    //   drag: function() {
    //     counts[ 1 ]++;
    //     updateCounterStatus( $drag_counter, counts[ 1 ] );
    //   },
    //   stop: function() {
    //     counts[ 2 ]++;
    //     updateCounterStatus( $stop_counter, counts[ 2 ] );
    //   }
    // });


            div_cell.resize(function(){

                var fg = 45;

            });

            var scale_width = 0;
            // var object_width = $('.task-gantt-timeline-data').width();
            var scroll_width = 0;





            div_cell.draggable({
                axis: "x",

                containment: ".timeline-gantt-scroll-scale",
                scroll: false,

                start: function () {

                    scale_width = $('.timeline-gantt-scroll-scale').width();
                    // object_width = $('.task-gantt-timeline-data').width();
                    var x1 = $('.task-gantt-timeline').width();
                    var x2 = $('.task-gantt-timeline-data').width();
                    scroll_width = x2 - x1;

                    // object_width = $('.task-gantt-timeline-data').scrollWidth - $('.task-gantt-timeline-data').clientWidth;

                    var er = 45;


                },

                drag: function() {

                    self.updateCounterStatus( div_cell, scale_width, scroll_width);
                },

            });

        var parent = this.__parentedParent;


        var scroll_start_dt = new Date(0);
        scroll_start_dt.setTime(parent.firstDayDate);

        var scroll_end_dt = new Date(0);
        scroll_end_dt.setTime(parent.lastDayDate);

        var l10n = _t.database.parameters;
        var formatDate = time.strftime_to_moment_format( l10n.date_format + ' ' + l10n.time_format);

        var scroll_start_str = moment(scroll_start_dt).format(formatDate);
        var scroll_end_str = moment(scroll_end_dt).format(formatDate);
        // var scroll_start = (tleft*this.parent.pxScaleUTC)+this.parent.firstDayScale;
        // var scroll_end = (tright*this.parent.pxScaleUTC)+this.parent.firstDayScale;
        //
        //
        // var new_task_start = new Date(0); // The 0 there is the key, which sets the date to the epoch setUTCSeconds(task_start);
        // new_task_start.setTime(task_start);

                 // div_cell.addClass('draggable ui-widget-content');

            var bar_start = $('<div class="timeline-gantt-scroll-scale-start"></div>');
            var bar_end = $('<div class="timeline-gantt-scroll-scale-end"></div>');

            $('<div class="timeline-gantt-scroll-scale-start-date">'+scroll_start_str+'</div>').appendTo(bar_start);
            $('<div class="timeline-gantt-scroll-scale-end-date">'+scroll_end_str+'</div>').appendTo(bar_end);

            el.append(bar_start);
            el.append(bar_end);

            el.append(div_cell);

            // _.each(this.second_scale, function(day){
            //
            //     var div_cell ='';
            //
            //     div_cell = $('<span class="task-gantt-bottom-column">'+moment(day).date()+'</span>');
            //     div_cell.css({ width: self.timeScale + "px" });
            //
            //     if (moment(day).isoWeekday() === 6 || moment(day).isoWeekday() === 7){
            //         div_cell.addClass('task-gantt-weekend-column');
            //     }
            //
            //     if (moment(day).isSame(self.TODAY, 'day')){
            //         div_cell.addClass('task-gantt-today-column');
            //     }
            //
            //     return  el_scale_secondary.append(div_cell);
            //
            // });
            //
            // _.each(this.first_scale, function(month){
            //
            //
            //          var monthScale = self.timeScale*month.days;
            //
            //          var div_cell = $('<span class="task-gantt-top-column"></span>');
            //
            //           div_cell.css({ width: monthScale + "px" });
            //
            //          div_cell.append($('<span class="task-gantt-scale-month-text">' + month.year + ' - ' + month.month + '</span>'));
            //
            //          return el_scale_primary.append(div_cell);
            //
            // });

        //}





        // if (this.timeType === 'day_1hour' ||
        //     this.timeType === 'day_2hour' ||
        //     this.timeType === 'day_4hour' ||
        //     this.timeType === 'day_8hour' ) {
        //
        //
        //
        //     _.each(this.first_scale, function(range_date , rdate){
        //
        //
        //        var dm =  moment(rdate).format("Do MMM dd - YY");
        //
        //         var monthScale = self.timeScale*range_date.length;
        //
        //         var div_cell = $('<span class="task-gantt-top-column"></span>');
        //             div_cell.css({ width: monthScale + "px" });
        //             div_cell.append($('<span class="task-gantt-scale-month-text">'+dm+'</span>'));
        //
        //             el_scale_primary.append(div_cell);
        //
        //
        //         _.each(range_date, function(hour){
        //
        //                 var div_cell ='';
        //
        //                var hours_string =  moment(hour).format("HH:mm");
        //
        //                 div_cell = $('<span class="task-gantt-bottom-column">'+hours_string+'</span>');
        //                 div_cell.css({ width: self.timeScale + "px" });
        //
        //                 if (moment(hour).isoWeekday() === 6 || moment(hour).isoWeekday() === 7){
        //                     div_cell.addClass('task-gantt-weekend-column');
        //                 }
        //
        //                 if (moment(hour).isSame(self.TODAY, 'day')){
        //                     div_cell.addClass('task-gantt-today-column');
        //                 }
        //
        //                 el_scale_secondary.append(div_cell);
        //
        //         });
        //
        //
        //         }
        //     );
        //
        // }
        //
        //
        //
        //
        //
        // if (this.timeType == 'month_day')
        // {
        //
        //
        //     _.each(this.second_scale, function(day){
        //
        //         var div_cell ='';
        //
        //         div_cell = $('<span class="task-gantt-bottom-column">'+moment(day).date()+'</span>');
        //         div_cell.css({ width: self.timeScale + "px" });
        //
        //         if (moment(day).isoWeekday() === 6 || moment(day).isoWeekday() === 7){
        //             div_cell.addClass('task-gantt-weekend-column');
        //         }
        //
        //         if (moment(day).isSame(self.TODAY, 'day')){
        //             div_cell.addClass('task-gantt-today-column');
        //         }
        //
        //         return  el_scale_secondary.append(div_cell);
        //
        //     });
        //
        //     _.each(this.first_scale, function(month){
        //
        //
        //              var monthScale = self.timeScale*month.days;
        //
        //              var div_cell = $('<span class="task-gantt-top-column"></span>');
        //
        //               div_cell.css({ width: monthScale + "px" });
        //
        //              div_cell.append($('<span class="task-gantt-scale-month-text">' + month.year + ' - ' + month.month + '</span>'));
        //
        //              return el_scale_primary.append(div_cell);
        //
        //     });
        //
        // }
        //
        //
        // if (this.timeType == 'month_week') {
        //
        //
        //     _.each(this.first_scale, function(range_date , rdate){
        //
        //
        //        var dm =  moment(rdate).format("YYYY");
        //
        //         var monthScale = self.timeScale*range_date.length;
        //
        //         var div_cell = $('<span class="task-gantt-top-column"></span>');
        //             div_cell.css({ width: monthScale + "px" });
        //             div_cell.append($('<span class="task-gantt-scale-month-text">'+dm+'</span>'));
        //
        //             el_scale_primary.append(div_cell);
        //
        //
        //         _.each(range_date, function(hour){
        //
        //                 var div_cell ='';
        //
        //                var week_string =  moment(hour).format("W");
        //
        //                 div_cell = $('<span class="task-gantt-bottom-column">'+week_string+'</span>');
        //                 div_cell.css({ width: self.timeScale + "px" });
        //
        //                 el_scale_secondary.append(div_cell);
        //         });
        //
        //     });
        //
        // }
        //
        //
        // if (this.timeType == 'quarter') {
        //
        //
        //     _.each(this.first_scale, function(range_date , rdate){
        //
        //
        //        var dm =  moment(rdate).format("YYYY");
        //
        //         var monthScale = self.timeScale*range_date.length;
        //
        //
        //
        //         var div_cell = $('<span class="task-gantt-top-column"></span>');
        //             div_cell.css({ width: monthScale + "px" });
        //             div_cell.append($('<span class="task-gantt-scale-month-text">'+dm+'</span>'));
        //
        //             el_scale_primary.append(div_cell);
        //
        //
        //         _.each(range_date, function(quarter){
        //
        //                 var div_cell ='';
        //
        //                var week_string =  moment(quarter).format("Q");
        //
        //                 div_cell = $('<span class="task-gantt-bottom-column">'+week_string+'</span>');
        //                 div_cell.css({ width: self.timeScale + "px" });
        //
        //                 el_scale_secondary.append(div_cell);
        //         });
        //
        //     });
        //
        //
        // }
        //
        //
        //
        // if (this.timeType == 'year_month') {
        //
        //
        //     _.each(this.first_scale, function(range_date , rdate){
        //
        //
        //        var dm =  moment(rdate).format("YYYY");
        //
        //         var monthScale = self.timeScale*range_date.length;
        //
        //
        //
        //         var div_cell = $('<span class="task-gantt-top-column"></span>');
        //             div_cell.css({ width: monthScale + "px" });
        //             div_cell.append($('<span class="task-gantt-scale-month-text">'+dm+'</span>'));
        //
        //             el_scale_primary.append(div_cell);
        //
        //
        //         _.each(range_date, function(quarter){
        //
        //                 var div_cell ='';
        //
        //                var week_string =  moment(quarter).format("MMM");
        //
        //                 div_cell = $('<span class="task-gantt-bottom-column">'+week_string+'</span>');
        //                 div_cell.css({ width: self.timeScale + "px" });
        //
        //                 el_scale_secondary.append(div_cell);
        //         });
        //
        //     });
        //
        // }





    }



});

return GanttTimeLineScroll;

});