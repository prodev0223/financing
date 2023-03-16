robo.define('robo.tourHolidays', function(require) {
"use strict";

var core = require('web.core');
var tour = require('robo.tour');

var _t = core._t;

//trigger- matomas elementas kuris laukia "paspaudimo ar pan"
//extra_trigger - elementas kuris turi buti matomas, kad trigger butu matomas
var steps = [
    {
        content: _t('Per šį meniu galite greitai sukurti naują <i>atostogų prašymą</i>'),
        trigger: '.o_main .o_sub_menu a[data-menu-name="Robo Vadovas"]',
        position: 'bottom',
        space: -5,
        width: 350,
        animation: 'animation-robo-border',
    },
    {
        content: _t("Norėdami sukurti <i>atostogų prašymą</i> įveskite žodį <b>atostogos</b>"),
        trigger: '.robo-search .search-box #search2',
        position: 'top',
        width: 380,
    },
    {
        content: _t("Pasirinkite"),
        trigger: '.results a:containsExact(Prašymas dėl kasmetinių atostogų)',
        //tag <a> robo paieškos rezultatuose turi special klasę. Todėl šis step įvykdomas per "click" event, o ne per "mouseDown" kaip įprastai!
        position: 'left',
        width: 140,
        animation: 'animation-robo-border',
    },
    {
        content: _t("Čia galėsite <b>patvirtinti</b> ir po to <b>pasirašyti</b> prašymą"),
        trigger: '.o_form_statusbar .o_statusbar_buttons:has(button:not(.o_form_invisible) span:containsExact(Patvirtinti))',
        extra_trigger: '.o_form_view .oe_title .o_form_field:containsExact(Prašymas dėl kasmetinių atostogų)',
        position: 'left',
        width: 200,
    },
    {
        content: _t("Dabar galite <b>pasirašyti</b> dokumentą"),
        trigger: '.o_form_statusbar .o_statusbar_buttons:has(button:not(.o_form_invisible) span:containsExact(Pasirašyti))',
        extra_trigger: '.o_form_view .oe_title .o_form_field:containsExact(Prašymas dėl kasmetinių atostogų)',
        position: 'top',
        width: 230,
    },

];

var steps_state_info =[
    {
        content: _t("Paspauskite ir matysite galimus dokumento statusus"),
        trigger: '.o_form_statusbar .o_statusbar_status',
        extra_trigger: '.o_form_view .oe_title .o_form_field:containsExact(Prašymas dėl kasmetinių atostogų)',
        position: 'top',
        width: 200,
    }
];

tour.register('robo_new_Holidays_tour', {skip_enabled: true}, steps);
tour.register('robo_new_Holidays_tour_document_state_info', {skip_enabled: true}, steps_state_info);
// tour.run('robo_new_Holidays_tour',3000);

});

