robo.define('robo.CrashManager', function (require) {
    "use strict";

    var ajax = require('web.ajax');
    var core = require('web.core');
    var Dialog = require('web.Dialog');
    var CrashManager = require('web.CrashManager');
    var session = require('web.session');

    var _t = core._t;
    var QWeb = core.qweb;

    CrashManager.include({
       _browser_info: function(){
            var sBrowser, sUsrAg = navigator.userAgent;

            if(sUsrAg.indexOf("Chrome") > -1) {
                sBrowser = "Google Chrome";
            } else if (sUsrAg.indexOf("Safari") > -1) {
                sBrowser = "Apple Safari";
            } else if (sUsrAg.indexOf("Opera") > -1) {
                sBrowser = "Opera";
            } else if (sUsrAg.indexOf("Firefox") > -1) {
                sBrowser = "Mozilla Firefox";
            } else if (sUsrAg.indexOf("MSIE") > -1) {
                sBrowser = "Microsoft Internet Explorer";
            }

            return sBrowser;
       },
       show_error: function(error) {
           try {
               if (!this.active) {
                   return;
               }
               if (session.is_superuser) {
                   new Dialog(this, {
                       title: "robo " + _.str.capitalize(error.type),
                       $content: QWeb.render('CrashManager.error', {error: error, session: session})
                   }).open();
               }
               else if (!error.data || !(error.data.exception_type === 'internal_error')) {
                   var browser = this._browser_info();
                   if (error.message) {
                       error.message = QWeb.render('RoboCrashManager.error', {error: error, session: session, browser: browser});
                   }
                   ajax.jsonRpc('/web/send_front_error_message', 'call', error).then(function () {
                       error['message'] = 'Ups... Robo platformos klaidelė. Sistemos administratoriai informuoti. Prašome perkrauti puslapį.';
                       new Dialog(this, {
                           title: "robo " + _.str.capitalize(error.type),
                           $content: QWeb.render('RoboCrashManager.error', {error: error})
                       }).open();
                   });
               }
               else {
                   error['message'] = _t('Ups... Robo platformos klaidelė. Prašome perkrauti puslapį.');
                   new Dialog(this, {
                       title: "robo " + _.str.capitalize(error.type),
                       $content: QWeb.render('RoboCrashManager.error', {error: error})
                   }).open();
               }
           }
           //ROBO: in case error in error_handler
           catch(error){
               new Dialog(this, {
                           title: "robo",
                           $content: '<div><span>Ups... Robo platformos klaidelė. Jeigu klaida kartosis, kreipkitės į sistemos administratorių,</span></div>',
                   }).open();
           }
        },
    });

});