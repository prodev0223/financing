robo.define('robo_dashboard', function (require) {
    'use strict';

    var kanban_widgets = require('web_kanban.widgets');

    var RoboDashboardGraph = kanban_widgets.AbstractField.extend({
        start: function () {
            this.graph_type = this.$node.attr('graph_type');
            this.data = JSON.parse(this.field.raw_value);
            this.display_graph();
            return this._super();
        },

        display_graph: function () {
            var self = this;
            nv.addGraph(function () {
                self.$svg = self.$el.append('<svg>');

                switch (self.graph_type) {

                    case "bar":
                        self.$svg.addClass('o_graph_barchart');

                        self.chart = nv.models.discreteBarChart()
                            .x(function(d) { return d.label })
                            .y(function(d) { return d.value })
                            .showValues(false)
                            .showYAxis(true)
                            .margin({'left': 15, 'right': 10, 'top': 45, 'bottom': 40})
                        ;


                        self.chart.xAxis.axisLabel(self.data[0].title);
                        self.chart.xAxis.tickValues(['1', '5', '10', '15']);
                        self.chart.yAxis.axisLabel(self.data[0].title);
                        self.chart.yAxis.tickFormat(d3.format(',.0f'));

                        break;
                }
                d3.select(self.$el.find('svg')[0])
                    .datum(self.data)
                    .transition().duration(1200)
                    .call(self.chart);

                self.customize_chart();

                nv.utils.windowResize(self.on_resize);
            });
        },

        on_resize: function () {
            this.chart.update();
            this.customize_chart();
        },

        customize_chart: function () {
            if (this.graph_type === 'bar') {
                // Add classes related to time on each bar of the bar chart
                var bar_classes = _.map(this.data[0].values, function (v, k) {
                    return v.type
                });

                _.each(this.$('.nv-bar'), function (v, k) {
                    // classList doesn't work with phantomJS & addClass doesn't work with a SVG element
                    $(v).attr('class', $(v).attr('class') + ' ' + bar_classes[k]);
                });
            }
        },

        destroy: function () {
            nv.utils.offWindowResize(this.on_resize);
            this._super();
        },

    });

    kanban_widgets.registry.add('robo_dashboard_graph', RoboDashboardGraph);

});

robo.define('robo_dashboard_multi', function (require) {
'use strict';

var kanban_widgets = require('web_kanban.widgets');

var RoboDashboardGraphMulti = kanban_widgets.AbstractField.extend({
    start: function() {
        this.graph_type = this.$node.attr('graph_type');
        this.is_stacked = false;
        if (this.$node.attr('stacked') == 'true') {
            this.is_stacked = true;
        };
        var raw_data = JSON.parse(this.field.raw_value);
        this.data = raw_data.data;
//        this.show_legend = raw_data.options.show_legend;
        this.show_controls = raw_data.options.show_controls;
        this.display_graph();
        return this._super();
    },

    display_graph : function() {
        var self = this;
        nv.addGraph(function () {
            self.$svg = self.$el.append('<svg>');

            switch(self.graph_type) {

                case "bar":
                    self.$svg.addClass('o_graph_barchart');
                    self.chart = nv.models.multiBarChart()
                          .reduceXTicks(false)   //If 'false', every single x-axis tick label will be rendered.
                          .rotateLabels(0)      //Angle to rotate x-axis labels.
                          .showControls(self.show_controls)   //Allow user to switch between 'Grouped' and 'Stacked' mode.
                          .groupSpacing(0.1)    //Distance between each group of bars.
//                          .showLegend(self.show_legend)
//                          .stacked(self.is_stacked)
                          .margin({'left': 50, 'right': 10, 'top': 55, 'bottom': 40})
                          .height(225)
                        ;
                    self.chart.legend.color(function (d,i) {
                        return d.values[i].color;
                    });
                    self.chart.x(function(d) { return d.label; });
                    nv.utils.windowResize(self.chart.update);
                    self.chart.xAxis.axisLabel(self.data[0].title);
                    self.chart.stacked(true);
                    if (self.data.length > 0)
                        var nvalues = self.data[0].values.length;
                    else
                        var nvalues = 0;
                    if (nvalues >25){
                        var xvalues = ['1', '5', '10', '15', '20', '25', nvalues.toString()];
                        }
                    else
                        var xvalues = ['1', '5', '10', '15', '20', '25'];
                    self.chart.xAxis.tickValues(xvalues);
                    self.chart.yAxis.tickFormat(d3.format(',.0f'));
                    break;
            }
            d3.select(self.$el.find('svg')[0])
                .datum(self.data)
                .transition().duration(1200)
                .attr('height', 250)
                .call(self.chart);

            self.customize_chart();

            nv.utils.windowResize(self.on_resize);
        });
    },

    on_resize: function(){
        this.chart.update();
        this.customize_chart();
    },

    customize_chart: function(){
        if (this.graph_type === 'bar') {
            // Add classes related to time on each bar of the bar chart
            var bar_classes = _.map(this.data[0].values, function (v, k) {return v.type});

            _.each(this.$('.nv-bar'), function(v, k){
                // classList doesn't work with phantomJS & addClass doesn't work with a SVG element
                $(v).attr('class', $(v).attr('class') + ' ' + bar_classes[k]);
            });
        }
    },

    destroy: function(){
        nv.utils.offWindowResize(this.on_resize);
        this._super();
    },

});

kanban_widgets.registry.add('robo_dashboard_graph_multi', RoboDashboardGraphMulti);

});