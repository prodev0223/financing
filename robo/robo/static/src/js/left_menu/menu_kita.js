 robo.define('robo.menu_kita', function (require) {
     "use strict";
     var core = require('web.core');

     var Qweb = core.qweb;

     function Menu_kita (my_target, self) {
         this.popover_template = '<div class="popover robo-kita-menu-popover" role="tooltip"><div class="popover-arrow"></div><div class="popover-content"></div></div>';
         this.target = my_target;
         var target_class_selector = '.'+my_target.attr('class').split(' ').join('.');

         this.target.popover({
              // title: 'Menu',
              placement: 'right',
              container: 'body',
              trigger: 'manual',
              html: true,
              template: this.popover_template,
              content: Qweb.render('kitaMenuPopover', {menus: findMenus(my_target.parent())}),
         });

         core.bus.on('click', self, function(e){
           if ($(e.target).closest(target_class_selector).length === 0 && $(e.target).closest('.robo-kita-menu-popover').length === 0){
               my_target.popover('hide');
           }else if ($(e.target).closest('.robo-kita-menu-popover').length !== 0){
                   var menu_id = $(e.target).closest('div[data-menu].robo-kita-menu-item').data('menu');
                   my_target.parent().find('a[data-menu="' + menu_id + '"]').click();
           }
         });

     }

     Menu_kita.prototype.click = function(){
        this.target.popover('toggle');
     }

     function findMenus($searchPlace){
         var list=[];
         $searchPlace.find('a[data-menu]').each(function(index, m){
             list.push({id: $(m).data('menu'), name: $(m).data('menu-name'), icon: $(m).find("span[data-menu-icon]").data('menu-icon')});
         });
         return list;
     }

     return Menu_kita;
 });