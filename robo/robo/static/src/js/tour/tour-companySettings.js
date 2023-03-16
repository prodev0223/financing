robo.define('robo.tourcompanySettings', function(require) {
"use strict";

var core = require('web.core');
var session = require('web.session');
var tour = require('robo.tour');

var _t = core._t;

var steps = [
    {
        trigger: '.o_sub_menu_logo i.robo-logo-toggle-icon',
        // extra_trigger: '.o_sub_menu_logo .robo-logo-toggle-icon',
        content: _t('Užpildykite <b>kompanijos informaciją</b>'),
        position: 'bottom',
        space: 5,
        // animation: 'animation-robo-border',
        width: 240,
    },
    {
        trigger: '.company-settings .logo-dropdown-menu:has(.logo-menu-item[data-menu=company_setup])',
        extra_trigger: '.o_sub_menu_logo .my-Popover',
        content: _t('Jūsų kompanijos nustatymai'),
        position: 'right',
        width: 200,
    },
    {
        trigger: '.o_form_statusbar .o_statusbar_buttons .btn-group',
        extra_trigger: '.o_form_view.robo_company_settings',
        content: _t('Užpildykite žemiau esančius duomenis ir <b>išsaugokite</b>'),
        position: 'left',
        width: 240,
    },
];


//please register without any promises, as tour service registers tours for mutations just after DOM loading
tour.register('robo_company_settings', {skip_enabled: true, only_for: $.when(session.is_manager())},  steps);


});

