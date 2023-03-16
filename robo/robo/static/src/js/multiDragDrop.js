robo.define('robo.MultiDragDrop', function (require) {
    "use strict";


    // var data = require('web.data');
    // var DragDropMixin = require('robo.expenses').DragDropMixin;
    var bus = require('bus.bus').bus;
    var config = require('web.config');
    var core = require('web.core');
    var Model = require('web.DataModel');
    var session = require('web.session');
    var Widget = require('web.Widget');
    var utils = require('web.utils');

    var QWeb = core.qweb;

    var MultiDragDrop = Widget.extend({
        template: "MultiDragDropXML",
        init: function(){
          this._super.apply(this, arguments);
          this.model = new Model('hr.expense');
          this.uploaded_files = new Model('robo.upload');
          window.Dropzone.autoDiscover = false;
          this.recently_uploaded = [];
          this.dp = new utils.DropPrevious();
          this.states = {};
          this.robo_alias_model = new Model('res.company');
          // this.start_month = moment().startOf('month').format('YYYY-MM-DD');
          // this.end_month = moment().endOf('month').format('YYYY-MM-DD');
        },
        willStart: function(){
          var self = this;
          this.is_screen_big = (config.device.size_class > config.device.SIZES.XS) || false;

          return $.when(this._super()).then(function(){
                return self.uploaded_files.call("fields_get",[['state']]);
          }).then(function(results){
             if (results && results.state && results.state.selection){
                 results.state.selection.forEach(function(el){
                     self.states[el[0]] = el[1]
                 })
             }
             return $.when(self._update());
          }).then(function(){
              var def = self.robo_alias_model.query(['robo_alias'])
                            .filter([['id', '=', session.company_id]])
                            .limit(1)
                            .all()
              return $.when(def).then(function(r){
                     self.robo_alias = r[0].robo_alias;
              });
          });
            // this.states.sent = 'Išsiųstas';
            // this.states.accepted = 'Priimtas';
            // this.states.done = 'Apdorotas';
            // return $.when();

        },
        _update: function(){
            var self = this;
            var def = this.uploaded_files.query(['datas_fname', 'mimetype', 'state', 'person'])
                .order_by('-create_date')
                .limit(4).all()
                .then(function(records){
                    self.recently_uploaded.length = 0; //clear array
                    _.each(records, function (record) {
                        self.recently_uploaded.push(record);
                    });
                });
            return $.when(def)
        },
        update_counter: function(){
            var self = this;
            var start = moment().startOf('month').format('YYYY-MM-DD'),
                end = moment().endOf('month').format('YYYY-MM-DD 23:59:59');
            return this.rpc('/roboupload/statistics', {start: start, end: end}).then(function(counter) {
                if (_.isObject(counter)) {
                    self.$('.robo-statistics .accepted .statistics-number').text(counter.accepted);
                    self.$('.robo-statistics .done .statistics-number').text(counter.done);
                    self.$('.robo-statistics .rejected .statistics-number').text(counter.rejected);
                    self.$('.robo-statistics .need_action .statistics-number').text(counter.need_action);
                }
            });
        },
        start: function(){
            var self = this;
            bus.on('notification', this, function (notifications) {
                _.each(notifications, (function (notification) {
                    if (notification[0][1] === 'robo.upload') {
                        this.update_counter();
                    }
                }).bind(this));
            });
            var $dropzone = this.$('.dropzone');
            var acceptedMimes = [
                'application/pdf',
                'application/postscript',
                'image/*',
                '.doc','.docx','.xls', '.xlsx', '.msg',
                '.odt', '.ods', '.odi', '.xml',
                'text/plain', 'text/xml',
                '.zip', '.rar', '.tar', '.7z',
                '.rtf', '.csv'
                ]
            var zone = $dropzone.dropzone({
                url: '/robo/upload',
                paramName: 'ufile',
                acceptedFiles: acceptedMimes.join(','),
                // done: Reikia priimti visus failus, negali buti tokios zinutes!
                dictInvalidFileType: "Negalite pateikti tokio tipo dokumento.",
                dictResponseError: "Serverio klaida {{statusCode}}. Pabandykite dar kartą.",
                dictCancelUpload: "Nutraukti pateikimą",
                dictCancelUploadConfirmation: "Ar tikrai norite nutraukti pateikimą?",
                dictRemoveFile: "pašalinti",
                // addRemoveLinks: true,
                success: function(file, response){
                    if (response === 'success'){
                        if (file.previewElement) {
                          return file.previewElement.classList.add("dz-success");
                        }
                    }
                    else{
                        var node, _i, _len, _ref, _results, message=response;
                        if (file.previewElement) {
                          file.previewElement.classList.add("dz-error");
                          _ref = file.previewElement.querySelectorAll("[data-dz-errormessage]");
                          _results = [];
                          for (_i = 0, _len = _ref.length; _i < _len; _i++) {
                            node = _ref[_i];
                            _results.push(node.textContent = message);
                          }
                          return _results;
                        }
                    }
                },
                sending: function(file, xhr, formData){
                    var fileupload_id = _.uniqueId('fileupload_id');
                    formData.append('csrf_token', core.csrf_token);
                    formData.append('callback', fileupload_id);
                }
            });
            this.attach_tooltip(); //after rendering
            this.attach_tooltip_info();
            return $.when(this._super(), this.update_counter()).then(function(){
               self.$el.on('click','.show_all_files',function(e){
                   e.preventDefault();
                   e.stopPropagation();
                   self.do_action('robo.show_all_files', {'clear_breadcrumbs': true});
               });
               var upload_types = {
                 '.accepted': {'search_default_accepted':1},
                 '.done': {'search_default_done':1},
                 '.rejected': {'search_default_rejected':1},
                 '.need_action': {'search_default_need_action':1},
               };
               _(upload_types).each(function(value, key){
                   self.$el.on('click','.robo-statistics '+key, function(e){
                       e.preventDefault();
                       e.stopPropagation();
                       self.do_action('robo.show_all_files', {'clear_breadcrumbs': true, 'additional_context': value});
                   });
               });

            });
        },
        _tooltip_html: function(uniq_id){
            return QWeb.render('robo.dragDrop.tooltip', {
                            files: this.recently_uploaded,
                            uniq_id: uniq_id,
                            states: this.states,
                            is_screen_big : (config.device.size_class > config.device.SIZES.XS) || false,
                           });
        },
        _tooltip_info_html: function(){
            return QWeb.render('doc-processing-info-dragdrop', {});
        },
        attach_tooltip_info: function(){
            var self = this;
            self.$el.find('.doc-processing-info').tooltip({
                html: true,
                delay: { show: 50, hide: 1000 },
                container: '.doc-processing-info',
                title: function(){
                    return self._tooltip_info_html();
                },
            });
        },
        attach_tooltip: function(){
            var self = this;
            self.$el.tooltip({
                html: true,
                delay: { show: 50, hide: 1000 },
                container: '.multiDragDrop',
                title: function(){
                    var uniq_id = _.uniqueId('tooltipDragDrop_');
                    var fetch_def = self.dp.add(self._update());
                    utils.reject_after(fetch_def, utils.delay(500)).then(function(){
                        var my_html = self._tooltip_html(uniq_id);
                        self.$('#'+uniq_id).parent().html(my_html);
                    });
                    return self._tooltip_html(uniq_id);
                },
            });
        },
        destroy: function(){
            if (this.$('.dropzone')[0]){
                this.$('.dropzone')[0].dropzone.destroy();
            }
            this._super();

        },
    });
    return MultiDragDrop;
});
