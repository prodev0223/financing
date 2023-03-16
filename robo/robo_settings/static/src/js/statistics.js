robo.define('robo_settings.statistics', function (require) {
    "use strict";

var ajax = require('web.ajax');
var config = require('web.config');
var core = require("web.core");
var session = require("web.session");
var utils = require('web.utils');
require("robo.session");


var bus = core.bus;
var UPDATE_INTERVAL = 120;//in s; how often we try to send statistics to DB
var MINIMUM_USAGE_TIME = 10;//in s; minimum usage (focus) time of application - it prevents sending "small usage" statistics to DB
var last_time_used_keyboard;
var last_time_used_mouse;

var wait_job_finish = new utils.Mutex();
var send_interval; //setInterval id
var inactivity_time;


if (config.device.size_class <= config.device.SIZES.XS ){
    return $.Deferred().reject();
}


var statistics = (function(){
    window.addEventListener('onload', start_timer);
    document.addEventListener('onmousemove', start_timer);
    document.addEventListener('onkeydown', start_timer);
    document.onmousemove = start_timer;
    document.onmousedown = start_timer;
    document.addEventListener('ontouchstart', start_timer);
    document.addEventListener('onclick', start_timer);
    document.addEventListener('onkeydown', start_timer);
    document.addEventListener('focus', start_timer);
    document.addEventListener('scroll', start_timer, true);
    var curr={
        type: null, /*tags or models*/
        val: null,
    };
    var total_usage_time = 0;
    var start_time;

    var data = {
        models: {},
        tags: {},
    };

    function add(val, type){
        // if (typeof type != 'string' && (type == 'tags' || type == 'models') && typeof val != 'string'){ return;}
        if (curr.type === type && curr.val === val){
            return;
        }
        else{
            stop_timer();
            curr.type = type;
            curr.val = val;
            start_time = new Date();
        }
    };

    function calculate_time(){
        if (curr.type && curr.val && start_time){
            var end_time = new Date();
            var duration = end_time.getTime() - start_time.getTime();
            if (data[curr.type][curr.val]){
                data[curr.type][curr.val] += duration
            }
            else{
                duration>0 ? (data[curr.type][curr.val] = duration) : undefined;
            }
            total_usage_time += duration;
        }
    };

    function reset_active_action(){
        curr.type = null;
        curr.val = null;
    };

    function reset_start_timer(){
        start_time = null;
    }

    function stop_timer(){
        calculate_time();
        reset_start_timer();
    };

    function start_timer(){
        if (!start_time) start_time = new Date();
        resetInActivityTimer();
    };

    function stop_inactivity() {
        statistics.stop_timer();
    }

    function resetInActivityTimer() {
        clearTimeout(inactivity_time);
        inactivity_time = setTimeout(stop, 1000 * 60 * 5)
    }

    function print(){
        return JSON.parse(JSON.stringify(data, function(k,v){
            if (typeof v == "number"){
                var d =  ~~(v/1000);
                if (d > 0){ return d; }
            }
            else{
                return v;
            }
        }));
    };

    function enough_accumulated_time(){
        return total_usage_time >= MINIMUM_USAGE_TIME*1000 //both in ms
    };

    function reset_accumulated_time(){
        total_usage_time = 0;
    };

    function reset_statistics(){
        data = {
            models: {},
            tags: {}
        };
    };

    return {
        add: add,
        stop_timer: stop_timer,
        start_timer: start_timer,
        reset_active_action: reset_active_action,
        reset_start_timer: reset_start_timer,
        reset_statistics: reset_statistics,
        print: print,
        enough_accumulated_time: enough_accumulated_time,
        reset_accumulated_time: reset_accumulated_time,
        resetInActivityTimer: resetInActivityTimer
    }
})();

function start_action(action){
    if (action){
        if (action.res_model){
            statistics.add(action.res_model, 'models');
        }
        else if (action.tag){
            statistics.add(action.tag, 'tags');
        }
        else{
            statistics.add('other', 'models');
        }
    }
    if (!document.hasFocus()){
        statistics.reset_start_timer();
    }
    // console.log((action && (action.res_model) || action.tag));
};

function startActionTimer(){
    statistics.start_timer();
};

function stopActionTimer(){
    statistics.stop_timer();
};

function update_database(){
    //accumulate current action time
    statistics.stop_timer();

    if (!document.hasFocus()){
        statistics.reset_start_timer();
    }

    if (statistics.enough_accumulated_time()){
        statistics.reset_accumulated_time();
        wait_job_finish.exec(function(){
            ajax.rpc('/statistics/get_statistics', {data: statistics.print()});
        });
        statistics.reset_statistics()
    }
};

function connection_lost(){
    statistics.stop_timer();
    // statistics.reset_active_action();

    clearInterval(send_interval);
    send_interval = null;
};

function connection_restored(){
    if (!send_interval){
        send_interval = setInterval(update_database, UPDATE_INTERVAL*1000);
    }
};

return session.is_bound.then(function(){
    return session.accumulate_statistics()
}).then(function(get_statistics){
    if (get_statistics) {
        bus.on('action', null, start_action);
        $(window).on('focus', startActionTimer);
        $(window).on('blur', stopActionTimer);
        bus.on('connection_lost', null, connection_lost);
        bus.on('connection_restored', null, connection_restored);
        send_interval = setInterval(update_database, UPDATE_INTERVAL*1000);
    }
    // return statistics;
});



});