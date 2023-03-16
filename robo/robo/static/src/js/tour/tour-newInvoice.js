robo.define('robo.tourInvoice', function(require) {
"use strict";

var core = require('web.core');
var session = require('web.session');
var tour = require('robo.tour');

var _t = core._t;

var steps = [
    {
        trigger: '.o_main .o_sub_menu a[data-menu-name="Pajamos"]',
        content: _t('Išrašykite naują <i>sąskaitą faktūrą</i>'),
        position: 'bottom',
        space: -5,
        animation: 'animation-robo-border',
        width: 240,
    },
    {
        trigger: '.o_main .boxes .boxes-row .box-template.create-record',
        content: _t('Galite sukurti naują sąskaitą faktūrą'),
        extra_trigger: '.o_control_panel .robo_header h1.heading-text:containsExact(Kliento sąskaitos faktūros)',
        position: 'left',
        width: 240,
    },
    {
        content: _t("Pasirinkite <b>pirkėją</b>"),
        trigger: 'table.right_group tr:contains(Pavadinimas) .o_form_input_dropdown',
        extra_trigger: '.o_form_view.robo_pajamos_form',
        position: 'top',
        width: 140,
        animation: 'animation-robo-border',
    },
    {
        content: _t("Pridėkite <b>sąskaitos faktūros eilutę</b>"),
        trigger: 'td.o_form_field_x2many_list_row_add a:containsExact(Pridėti eilutę)',
        extra_trigger: '.o_form_view.robo_pajamos_form ',
        position: 'bottom',
        width: 220,
        animation: 'animation-robo-border',
    },
    {
        content: _t("<b>Patvirtinkite </b>sąskaitą faktūrą"),
        trigger: '.o_form_statusbar .o_statusbar_buttons:has(button:not(.o_form_invisible) span:containsExact(Patvirtinti))',
        extra_trigger: '.o_form_view.robo_pajamos_form ',
        position: 'left',
        width: 200,
    }
];

tour.register('robo_new_invoice_tour', {skip_enabled: true, only_for: $.when(session.is_manager())},  steps);


});

