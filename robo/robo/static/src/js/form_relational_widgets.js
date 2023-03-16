robo.define('robo.form_relational', function (require) {
    "use strict";

    var core = require('web.core');
    var data = require('web.data');
    var Dialog = require('web.Dialog');
    var form_common = require('web.form_common');
    var FormRelational = require('web.form_relational');
    var Model = require('web.DataModel');
    var DragDropMixin = require('robo.expenses').DragDropMixin
    var utils = require('web.utils');
    var Widget = require('web.Widget');

    var _t = core._t;
    var FieldMany2ManyBinaryMultiFiles = core.form_widget_registry.get('many2many_binary');
    var ReloadContext = core.action_registry.get("reload_context");
    var QWeb = core.qweb;

    var RoboM2ODialog = Dialog.extend({
        template: "RoboM2ODialog",
        init: function (parent) {
            this.name = parent.string;
            this._super(parent, {
                title: _.str.sprintf(_t("Create a %s"), parent.string),
                size: 'medium',
                buttons: [
                    {
                        text: _t('Create'), classes: 'btn-primary', click: function (e) {
                        if (this.$("input").val() !== '') {
                            this.getParent()._quick_create(this.$("input").val());
                            this.close();
                        } else {
                            e.preventDefault();
                            this.$("input").focus();
                        }
                    }
                    },

                    {
                        text: _t('Cancel'), click: function () {
                        this.getParent().$input.val('');
                        this.close();
                    }
                    }
                ]
            });
        },
        start: function () {
            var text = _.str.sprintf(_t("Norite sukurti naują %s, ar esate tikri, kad toks dar neegzistuoja?"), this.name);
            this.$("p").text(text);
            this.$("input").val(this.getParent().$input.val());
        },
    });

    var CompletionFieldMixinWithRekvizitai =  {
        init: function () {
            this.limit_rekv = 5;
            this.orderer_rekv = new utils.DropMisordered();
            this.dataModel_rekv = new Model('res.partner');
        },
        _modify_rekvizitai: function(r){
            return {
                partner_company_type: r.company_type,
                partner_email: r.email,
                partner_street: r.street,
                partner_city: r.city,
                partner_zip: r.zip,
                partner_kodas: r.kodas,
                partner_vat: r.vat,
                partner_phone: r.phone,
                // partner_category_id: r.category_id,
                partner_country_id: r.country_id,
                partner_fax: r.fax,
                partner_mobile: r.mobile,
                partner_website: r.website,
                partner_id: r.partner_id
            }
        },
        get_search_result_rekvizitai: function (search_val, database_result) {
            var self = this;
            var def = this.orderer_rekv.add(self.dataModel_rekv.call('vz_search', [search_val],{},{shadow: true}));
            return utils.reject_after(def, utils.delay(5000)).then(function (result) {
                // var counter=1;
                var values = _.map(result, function (x) {
                    return {
                        label: x.name,
                        value: x.name,
                        name: x.name,
                        kodas: x.kodas,
                        classname: 'rekvizitai-name o_m2o_dropdown_option',
                        action: function(){
                            //FieldMany2One return False in select $input.autocomplete, so input is not updated in focusout
                            if (this.label && this.kodas) {
                                $.when(this.label, self.dataModel_rekv.call('vz_read_dict', [this.kodas])).then(function (label, result) {
                                    var modf_result = self._modify_rekvizitai(result);
                                    return $.when(label, modf_result, self.field_manager.set_values(modf_result));
                                }).done(function (input_label, modf_result) {
                                    //quick create is modified in rekvizitai.py
                                    if (!modf_result.partner_id){
                                        self._quick_create(input_label);
                                    }else{
                                    self.field_manager.do_onchange(null);
                                    }
                                });
                            }
                        },
                    }
                });
                if (values.length > self.limit_rekv) {
                    values = values.slice(0, self.limit_rekv);
                }
                if (values.length > 0){
                    values.unshift({
                        label: 'Sukurti iš rekvizitai.lt:',
                        value: 'Rekviziai',
                        name: 'Rekvizitai',
                        kodas: '',
                        classname: 'o_m2o_dropdown_option_rekvizitai',
                        action: function() {},
                    })
                }
                return $.Deferred().resolve(database_result.concat(values));
            }, function(){
                return $.Deferred().resolve(database_result);
            });
        },
    };

    var RoboFieldMany2One = FormRelational.FieldMany2One.extend(CompletionFieldMixinWithRekvizitai, {
        show_error_displayer: function () {
            new RoboM2ODialog(this).open();
        },
        init: function(){
            this._super.apply(this, arguments);
            CompletionFieldMixinWithRekvizitai.init.call(this);
            //turn off focusout action
            this.ignore_focusout = true;
        },
        get_search_result: function(search_val){
            var self = this;
            return $.when(this._super(search_val)).then(function(db_result){
                return self.get_search_result_rekvizitai(search_val, db_result);
            });
        }
    });


    var RoboFieldMany2ManyBinaryMultiFiles = FieldMany2ManyBinaryMultiFiles.extend({
        template: "RoboFieldBinaryFileUploader",

        render_value: function() {
            var self = this;
            var my_pictures = [];
            this.read_name_values().then(function (ids) {
                self.$('.oe_placeholder_files, .oe_attachments')
                    .replaceWith($(QWeb.render('RoboFieldBinaryFileUploader.files', {'widget': self, 'values': ids})));


                // reinit input type file
                var $input = self.$('.o_form_input_file');
                $input.after($input.clone(true)).remove();
                self.$(".oe_fileupload").show();

                // display image thumbnail
                self.$(".o_image[data-mimetype^='image']").each(function () {
                    var $img = $(this);
                    if (/gif|jpe|jpg|png/.test($img.data('mimetype')) && $img.data('src')) {
                        // $img.css('background-image', "url('" + $img.data('src') + "')");
                        var robo_image = $img.find('img');
                        my_pictures.push(robo_image.attr('id'));
                        //+Math for force refresh
                        robo_image.attr({'src':$img.data('src')+"&"+(new Date()).getTime()}).show();

                    }
                });
                //remove img files not of image mimetype
                self.$(".o_image:not([data-mimetype^='image'])").find('img').remove();

                if (!self.get("effective_readonly")) {
                    //add icons
                    self.$('#darkroom-icons').html('<svg xmlns="http://www.w3.org/2000/svg">' +
                        '<symbol id="close" viewBox="0 0 24 24"><path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/><path d="M0 0h24v24H0z" fill="none"/></symbol>' +
                        '<symbol id="crop" viewBox="0 0 24 24"><path d="M0 0h24v24H0z" fill="none"/><path d="M17 15h2V7c0-1.1-.9-2-2-2H9v2h8v8zM7 17V1H5v4H1v2h4v10c0 1.1.9 2 2 2h10v4h2v-4h4v-2H7z"/></symbol>' +
                        '<symbol id="done" viewBox="0 0 24 24"><path d="M0 0h24v24H0z" fill="none"/><path d="M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z"/></symbol>' +
                        '<symbol id="redo" viewBox="0 0 24 24"><path d="M0 0h24v24H0z" fill="none"/><path d="M18.4 10.6C16.55 8.99 14.15 8 11.5 8c-4.65 0-8.58 3.03-9.96 7.22L3.9 16c1.05-3.19 4.05-5.5 7.6-5.5 1.95 0 3.73.72 5.12 1.88L13 16h9V7l-3.6 3.6z"/></symbol>' +
                        '<symbol id="rotate-left" viewBox="0 0 24 24"><path d="M0 0h24v24H0z" fill="none"/><path d="M7.11 8.53L5.7 7.11C4.8 8.27 4.24 9.61 4.07 11h2.02c.14-.87.49-1.72 1.02-2.47zM6.09 13H4.07c.17 1.39.72 2.73 1.62 3.89l1.41-1.42c-.52-.75-.87-1.59-1.01-2.47zm1.01 5.32c1.16.9 2.51 1.44 3.9 1.61V17.9c-.87-.15-1.71-.49-2.46-1.03L7.1 18.32zM13 4.07V1L8.45 5.55 13 10V6.09c2.84.48 5 2.94 5 5.91s-2.16 5.43-5 5.91v2.02c3.95-.49 7-3.85 7-7.93s-3.05-7.44-7-7.93z"/></symbol>' +
                        '<symbol id="rotate-right" viewBox="0 0 24 24"><path d="M0 0h24v24H0z" fill="none"/><path d="M15.55 5.55L11 1v3.07C7.06 4.56 4 7.92 4 12s3.05 7.44 7 7.93v-2.02c-2.84-.48-5-2.94-5-5.91s2.16-5.43 5-5.91V10l4.55-4.45zM19.93 11c-.17-1.39-.72-2.73-1.62-3.89l-1.42 1.42c.54.75.88 1.6 1.02 2.47h2.02zM13 17.9v2.02c1.39-.17 2.74-.71 3.9-1.61l-1.44-1.44c-.75.54-1.59.89-2.46 1.03zm3.89-2.42l1.42 1.41c.9-1.16 1.45-2.5 1.62-3.89h-2.02c-.14.87-.48 1.72-1.02 2.48z"/></symbol>' +
                        '<symbol id="save" viewBox="0 0 24 24" style="fill: red;fill-opacity: 0.7;"><path d="M0 0h24v24H0z" fill="none"/><path d="M17 3H5c-1.11 0-2 .9-2 2v14c0 1.1.89 2 2 2h14c1.1 0 2-.9 2-2V7l-4-4zm-5 16c-1.66 0-3-1.34-3-3s1.34-3 3-3 3 1.34 3 3-1.34 3-3 3zm3-10H5V5h10v4z"/></symbol>' +
                        '<symbol id="undo" viewBox="0 0 24 24"><path d="M0 0h24v24H0z" fill="none"/><path d="M12.5 8c-2.65 0-5.05.99-6.9 2.6L2 7v9h9l-3.62-3.62c1.39-1.16 3.16-1.88 5.12-1.88 3.54 0 6.55 2.31 7.6 5.5l2.37-.78C21.08 11.03 17.15 8 12.5 8z"/></symbol></svg>');
                    var darkroom_pictures = [];
                    my_pictures.forEach(function(r){
                        darkroom_pictures.push(new Darkroom("#"+r, {

                          maxWidth: 900,
                          // maxHeight: '480',
                          minWidth: 680,
                          ratio: 1,
                          // minHeight: '480',
                          plugins:{
                              save:{
                                  callback: function(){
                                    this.darkroom.selfDestroy();
                                    var image_id_str = _.str.strRightBack(r, '_');
                                    var image_id = _.str.toNumber(image_id_str);
                                    if (!_.isNaN(image_id) && self.data[image_id]){
                                        var img_conf = self.data[image_id];
                                        var url = this.darkroom.sourceCanvas.toDataURL();
                                        self.ds_file.write(image_id, {
                                            datas: url.replace(/^data:image\/(png|jpg);base64,/, ""),
                                            datas_fname: img_conf.datas_fname,
                                            mimetype: img_conf.mimetype,
                                            name: img_conf.name,
                                        });
                                    }
                                  }
                              },
                              crop:{},
                          },
                          initialize: function() {
                            // var cropPlugin = this.plugins['crop'];
                            // cropPlugin.requireFocus();
                          },
                        }));
                    });
                }
            });
        },
    });


    var RoboAttachFiles = form_common.FormWidget.extend(form_common.ReinitializeWidgetMixin, {
        template: 'roboAttachFilesXML',
        events: {
            'click .dz-image': 'file_click',
            'click .dz-details': 'file_click',
            'click .dz-robo-remove': 'file_remove',
        },
        init: function(){
            this._super.apply(this, arguments);
            this.ds_file = new data.DataSetSearch(this, 'ir.attachment');
            this.ds_file_wizard = new data.DataSetSearch(this, 'ir.attachment.wizard');
            this.prev_files = [];
            this.set({
                attachments: [],
                remove_link: !this.field_manager.get_field_value("attachment_drop_lock"),
            });
            this.res_o2m_drop = new utils.DropMisordered();
            this.render_drop = new utils.DropMisordered();

            this.field_manager.on("field_changed:user_attachment_ids", this, this.query_documents);
            this.field_manager.on("field_changed:attachment_drop_lock", this, function() {
                this.set({"remove_link": !this.field_manager.get_field_value("attachment_drop_lock")});
            });
            //ROBO: history clean conditions
            this.field_manager.on("load_record", this, this.reload_clean);

        },
        query_documents: function(){
            var self = this;
            var ids = this.field_manager.get_field_value("user_attachment_ids");
            if (ids && ids[0]){
                ids = ids[0][2]
            }
            else{
                return;
            }
            this.res_o2m_drop.add(this.ds_file.call('read', [ids, ['id', 'name', 'datas_fname', 'mimetype', 'file_size']]))
                .done(function(result){
                   if (result) {
                       result.forEach(function (el, indx) {
                           self.prev_files[indx] = el;
                       });
                       self.set({attachments: result});
                   }
                });
        },
        initialize_field: function() {
            //ROBO: do not want to renew on effective_readonly state change
            // form_common.ReinitializeWidgetMixin.initialize_field.call(this);

            this.initialize_content();
            this.on("change:attachments", this, this.reinitialize);
            this.on("change:remove_link", this, this.hide_remove_link);
            // ROBO: load_record trigger does this job
            // if (this.field_manager.pager){
            //     this.field_manager.pager.on("pager_changed", this, this.reload_clean);
            // }

        },
        reload_clean: function(){
          this.prev_files = [];
          this.reinitialize();
        },
        initialize_content: function(){
            var self = this;
            var acceptedMimes = [
                   'application/pdf',
                   'application/postscript',
                   'image/*',
                   '.doc','.docx','.xls', '.xlsx', '.msg',
                   '.odt', '.ods', '.odi',
                   'text/plain','text/xml'
               ];
            // var allow_remove = this.get('remove_link');
            this.dropzone_params ={
                url: '/web/binary/upload_attachment_invoice',
                params: {
                    'model': this.field_manager.model,
                    // 'id': parseInt(this.field_manager.datarecord.id, 10) || 0,
                    'wizard_id': this.field_manager.get_field_value('unique_wizard_id'),
                },
                paramName: 'ufile',
                maxFilesize: 50,
                maxFiles: 6,
                dictMaxFilesExceeded: _t("Negalite pateikti daugiau dokumentų."),
                acceptedFiles: acceptedMimes.join(','),
                dictDefaultMessage: "<span class='icon-copy'></span><span>" + _t("Nutempkite arba pasirinkite dokumentą") + "</span>",
                dictFileTooBig: _t("Failas per didelis") + " ({{filesize}}MiB). " + _t("Maksimalus dydis:") + " {{maxFilesize}}MiB.",
                dictInvalidFileType: _t("Negalite pateikti tokio tipo dokumento."),
                dictResponseError: _t("Serverio klaida") + " {{statusCode}}. " + _t("Pabandykite dar kartą."),
                dictCancelUpload: _t("Nutraukti pateikimą"),
                dictCancelUploadConfirmation: _t("Ar tikrai norite nutraukti pateikimą?"),
                clickable: true,
                prev_files: JSON.parse(JSON.stringify(self.prev_files)),
                thumbnailWidth: 30,
                thumbnailHeight: 30,
                previewTemplate: "<div class=\"dz-preview dz-file-preview\">\n  <div class=\"dz-image\"><img data-dz-thumbnail style='height:30px;width:30px;'/></div>\n  <div class=\"dz-details\">\n    <div class=\"dz-filename\"><span data-dz-name></span></div>\n  <div class=\"dz-size\"><span data-dz-size></span></div>\n</div>\n  <div class=\"dz-progress\"><span class=\"dz-upload\" data-dz-uploadprogress></span></div>\n  <div class=\"dz-error-message\"><span data-dz-errormessage></span></div>\n  <div class=\"dz-success-mark\">\n    <svg width=\"54px\" height=\"54px\" viewBox=\"0 0 54 54\" version=\"1.1\" xmlns=\"http://www.w3.org/2000/svg\" xmlns:xlink=\"http://www.w3.org/1999/xlink\" xmlns:sketch=\"http://www.bohemiancoding.com/sketch/ns\">\n      <title>Check</title>\n      <defs></defs>\n      <g id=\"Page-1\" stroke=\"none\" stroke-width=\"1\" fill=\"none\" fill-rule=\"evenodd\" sketch:type=\"MSPage\">\n        <path d=\"M23.5,31.8431458 L17.5852419,25.9283877 C16.0248253,24.3679711 13.4910294,24.366835 11.9289322,25.9289322 C10.3700136,27.4878508 10.3665912,30.0234455 11.9283877,31.5852419 L20.4147581,40.0716123 C20.5133999,40.1702541 20.6159315,40.2626649 20.7218615,40.3488435 C22.2835669,41.8725651 24.794234,41.8626202 26.3461564,40.3106978 L43.3106978,23.3461564 C44.8771021,21.7797521 44.8758057,19.2483887 43.3137085,17.6862915 C41.7547899,16.1273729 39.2176035,16.1255422 37.6538436,17.6893022 L23.5,31.8431458 Z M27,53 C41.3594035,53 53,41.3594035 53,27 C53,12.6405965 41.3594035,1 27,1 C12.6405965,1 1,12.6405965 1,27 C1,41.3594035 12.6405965,53 27,53 Z\" id=\"Oval-2\" stroke-opacity=\"0.198794158\" stroke=\"#747474\" fill-opacity=\"0.816519475\" fill=\"#85c51f\" sketch:type=\"MSShapeGroup\"></path>\n      </g>\n    </svg>\n  </div>\n  <div class=\"dz-error-mark\">\n    <svg width=\"54px\" height=\"54px\" viewBox=\"0 0 54 54\" version=\"1.1\" xmlns=\"http://www.w3.org/2000/svg\" xmlns:xlink=\"http://www.w3.org/1999/xlink\" xmlns:sketch=\"http://www.bohemiancoding.com/sketch/ns\">\n      <title>Error</title>\n      <defs></defs>\n      <g id=\"Page-1\" stroke=\"none\" stroke-width=\"1\" fill=\"none\" fill-rule=\"evenodd\" sketch:type=\"MSPage\">\n        <g id=\"Check-+-Oval-2\" sketch:type=\"MSLayerGroup\" stroke=\"#747474\" stroke-opacity=\"0.198794158\" fill=\"#E74C3C\" fill-opacity=\"0.816519475\">\n          <path d=\"M32.6568542,29 L38.3106978,23.3461564 C39.8771021,21.7797521 39.8758057,19.2483887 38.3137085,17.6862915 C36.7547899,16.1273729 34.2176035,16.1255422 32.6538436,17.6893022 L27,23.3431458 L21.3461564,17.6893022 C19.7823965,16.1255422 17.2452101,16.1273729 15.6862915,17.6862915 C14.1241943,19.2483887 14.1228979,21.7797521 15.6893022,23.3461564 L21.3431458,29 L15.6893022,34.6538436 C14.1228979,36.2202479 14.1241943,38.7516113 15.6862915,40.3137085 C17.2452101,41.8726271 19.7823965,41.8744578 21.3461564,40.3106978 L27,34.6568542 L32.6538436,40.3106978 C34.2176035,41.8744578 36.7547899,41.8726271 38.3137085,40.3137085 C39.8758057,38.7516113 39.8771021,36.2202479 38.3106978,34.6538436 L32.6568542,29 Z M27,53 C41.3594035,53 53,41.3594035 53,27 C53,12.6405965 41.3594035,1 27,1 C12.6405965,1 1,12.6405965 1,27 C1,41.3594035 12.6405965,53 27,53 Z\" id=\"Oval-2\" sketch:type=\"MSShapeGroup\"></path>\n        </g>\n      </g>\n    </svg>\n  </div>\n</div>",

                init: function(){
                  var mockFile;
                  this.on('addedfile', function(file){
                     if (file && file.type && !file.type.match(/image.*/)){
                         if (file.type.match('application/pdf') || file.type.match('application/postscript')) {
                             this.emit('thumbnail', file, "/web/static/src/img/mimetypes/pdf.png");
                         }
                         else{
                             this.emit('thumbnail', file, "/web/static/src/img/mimetypes/unknown.png")
                         }
                     }
                  });
                  this.options.prev_files.forEach(function(file){
                      mockFile = { name: file.name, size: file.file_size, dataUrl: self.get_file_url(file.id), id: file.id, type: file.mimetype};
                      var dz = this;
                      this.files.push(mockFile);
                      this.emit("addedfile", mockFile);
                      $(mockFile.previewTemplate).find('.dz-image').data('id', file.id);
                      this.createThumbnailFromUrl(mockFile, mockFile.dataUrl);
                      this.emit("complete", mockFile);
                      this._updateMaxFilesReachedClass()
                  }, this)
                },
                success: function(file, response){
                    response = response && JSON.parse(response);
                    if (response && response.id > 0){
                        if (file.previewElement) {
                          $(file.previewTemplate).find('.dz-image').data('id', response.id);
                          self.add_remove_link($(file.previewTemplate));
                          return file.previewElement.classList.add("dz-success");
                        }
                    }
                    else if (response && response.wizard_id){
                        if (file.previewElement) {
                          $(file.previewTemplate).find('.dz-image').data('wizard_id', response.wizard_id);
                          self.add_remove_link($(file.previewTemplate));
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
                            _results.push(node.textContent = (message && message.error) || message);
                          }
                          return _results;
                        }
                    }
                },
                sending: function(file, xhr, formData){
                    formData.append('csrf_token', core.csrf_token);
                    formData.append('id', parseInt(self.field_manager.datarecord.id, 10) || 0);
                }
            };
            if (this.$('.dropzone').length) {
                if (!this.dropzone) {
                    this.dropzone = new Dropzone(this.$('.dropzone')[0], this.dropzone_params);
                    this.add_remove_link(this.$('.dz-preview.dz-complete'));
                }
            }
        },
        add_remove_link: function($element){
            var self = this;
            if ($element && $element.length){
                if (this.get('remove_link')) {
                    $element.each(function () {
                        this.appendChild(self.createElement("<a class=\"dz-robo-remove\" href=\"javascript:undefined;\" data-dz-remove>" + _t("Pašalinti") + "</a>"));
                    });
                }
            }
        },
        createElement: function(string){
            var div;
            div = document.createElement("div");
            div.innerHTML = string;
            return div.childNodes[0];
        },
         confirm : function(question, accepted, rejected) {
            if (window.confirm(question)) {
              return accepted();
            } else if (rejected != null) {
              return rejected();
            }
         },
        destroy_content: function(){
          if (this.dropzone) {
            this.dropzone.destroy();
            this.dropzone = undefined;
          }
        },
        hide_remove_link: function(){
            this.$('.dz-robo-remove').toggle(this.get('remove_link'));
        },
        file_click: function(e){
            var wizard=false;
            var target_el = $(e.currentTarget);
            var $id = target_el.data('id') || target_el.data('wizard_id');
            if (!$id) {
                target_el = $(e.currentTarget).parent().find('.dz-image') || $(e.currentTarget);
                $id = target_el.data('id') || target_el.data('wizard_id');
            }
            if (!target_el.data('id') && !!target_el.data('wizard_id')){
                wizard = true;
            }
            if ($id) {
                var id = JSON.parse($id);
                if (id) {
                    window.open(this.get_file_url(id, wizard), '_blank');
                }
            }
        },
        file_remove_dropzone: function(id, data_field){
            var self = this;
            _.each(this.dropzone.files, function(el) {
                if ($(el.previewElement).find('.dz-image').data(data_field) === id){
                    self.dropzone.removeFile(el);
                    return;
                }
            });
        },
        file_remove: function(e){
            var self = this;
            e.stopPropagation();
            e.preventDefault();
            var $file_image = $(e.currentTarget).siblings('.dz-image');
            var file_id = parseInt($file_image.data('id'));
            if (file_id){
              self.confirm(_t("Ar tikrai norite ištrinti šį priedą?"), function(){
                  self.ds_file.unlink(file_id);
                  self.file_remove_dropzone(file_id, 'id');
                  self.prev_files = _.filter(self.prev_files, function(el){return el.id !=file_id});
              });
            }
            var wizard_id = parseInt($file_image.data('wizard_id'));
            if (wizard_id) {
              self.ds_file_wizard.unlink(wizard_id);
              self.file_remove_dropzone(wizard_id, 'wizard_id');
}
        },
        get_file_url: function(id, wizard) {
            if (wizard){
                return '/web/content/wizard/' + id;
            }
            return '/web/content/' + id;
        },
    });

    core.form_custom_registry.add('robo_attach_files', RoboAttachFiles);
    core.form_widget_registry.add('robo_many2many_binary', RoboFieldMany2ManyBinaryMultiFiles);
    core.form_widget_registry.add('robo_many2one', RoboFieldMany2One);
});
