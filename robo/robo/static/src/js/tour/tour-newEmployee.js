robo.define('robo.tourEmployee', function(require) {
"use strict";

var core = require('web.core');
var session = require('web.session');
var tour = require('robo.tour');

var _t = core._t;

var steps = [
    {
        content: _t('Priimkite naują darbuotoją'),
        trigger: '.o_main .o_sub_menu a[data-menu-name="Darbuotojai"]',
        position: 'bottom',
        space: -5,
        animation: 'animation-robo-border',
        width: 170,
    },
    {
        content: _t('Spauskite norėdami <i>priimti naują darbuotoją</i>'),
        trigger: '.o_view_manager_content .robo_employees_buttons .employee-box .robo_button_new:has(.btn-header:containsExact(Naujas darbuotojas))',
        position: 'left',
    }
    ,{
        content: _t('Užpildykite duomenis ir priimkite darbuotoją'),
        trigger: '.alert.alert-info button:has(span:containsExact(Priimti į darbą))',
        extra_trigger:'.o_form_view.employee_new_form',
        position: 'top',
    }
    ,{
        content: _t("Užpildykite duomenis (kaip atlyginimas, prašymo data ir kt.) ir <b>patvirtinkite</b> bei <b>pasirašykite</b> įsakymą"),
        trigger: '.o_form_statusbar .o_statusbar_buttons:has(button:not(.o_form_invisible) span:containsExact(Patvirtinti))',
        extra_trigger: '.o_form_view .oe_title .o_form_field:containsExact(Įsakymas dėl priėmimo į darbą)',
        position: 'top',
        width: 350,
    },
    {
        content: _t("Dabar <b>pasirašykite</b> įsakymą"),
        trigger: '.o_form_statusbar .o_statusbar_buttons:has(button:not(.o_form_invisible) span:containsExact(Pasirašyti))',
        extra_trigger: '.o_form_view .oe_title .o_form_field:containsExact(Įsakymas dėl priėmimo į darbą)',
        position: 'top',
        width: 220,
    }
];

var steps_login = [
    {
        content: _t('Norėdami sukurti prisijungimą <i>naujam darbuotojui</i> prie <b>Robo sistemos</b>, pažymėkite varnelę'),
        //ROBO: commented trigger makes every page update crazy every second; something wrong with jquery or sizzy libary:)
        // trigger: '.o_group .o_inner_group:nth-child(2) tr:has(label:containsExact(Prisijungimas prie Robo)) input[type=checkbox]',
        trigger: '.o_group .robo_access_checkbox input[type=checkbox]',
        extra_trigger:'.o_form_view.employee_new_form',
        position: 'top',
        width: 350,
    }
];

tour.register('robo_new_employee_tour', {skip_enabled: true, only_for: $.when(session.is_manager())},  steps);
tour.register('robo_connection_login', {skip_enabled: true, only_for: $.when(session.is_manager())},  steps_login);


});

