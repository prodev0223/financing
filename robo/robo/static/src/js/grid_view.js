robo.define('web_grid', function (require) {
"use strict";

var Class = require('web.Class');
var View = require('web.View');
var Widget = require('web.Widget');

var core = require('web.core');
var data = require('web.data');
var Dialog = require('web.Dialog');
var form_common = require('web.form_common');
var formats = require('web.formats');
var time = require('web.time');
var Model = require('web.DataModel');
var utils = require('web.utils');
var session = require('web.session');
var pyeval = require('web.pyeval');

var patch = require('snabbdom.patch');
var h = require('snabbdom.h');

var _t = core._t;
var _lt = core._lt;

var Field = Class.extend({
    init: function (name, descr, arch) {
        this._field_name = name;
        this._descr = descr;
        this._arch = arch || {attrs: {}, children: []};
    },
    self: function (record) {
        return record[this._field_name];
    },

    name: function () {
        return this._field_name;
    },

    label: function (record) {
        return this.self(record);
    },
    value: function (record) {
        return this.self(record);
    },

    format: function (value) {
        var type = this._arch.attrs.widget || this._descr.type;

        return formats.format_value(value, { type: type });
    },
    parse: function (value) {
        var type = this._arch.attrs.widget || this._descr.type;

        return formats.parse_value(value, { type: type });
    },
});
var fields = { };

function into(object, path) {
    if (!_(path).isArray()) {
        path = path.split('.');
    }
    for (var i = 0; i < path.length; i++) {
        object = object[path[i]];
    }
    return object;
}

var GridView = View.extend({
    icon: 'fa-th',
    display_name: _lt("Lentelė"),
    view_type: 'grid',
    add_label: _lt("Pridėti eilutę"),
    events: {
        "click .o_grid_button_add": function(event) {
            var _this = this;
            event.preventDefault();

            var ctx = pyeval.eval('context', _this._model.context());
            var form_context = _this.get_full_context();
            var formDescription = _this.ViewManager.views.form;
            var p = new form_common.FormViewDialog(this, {
                res_model: _this._model.name,
                res_id: false,
                // TODO: document quick_create_view (?) context key
                view_id: ctx['quick_create_view'] || (formDescription && formDescription.view_id) || false,
                context: form_context,
                title: _this.add_label.toString(),
                disable_multiple_selection: true,
                default_name: '',
            }).open();
            p.on('create_completed', this, function () {
                _this._fetch();
            });
        },
        'keydown .o_grid_input': function (e) {
            // suppress [return]
            switch (e.which) {
            case $.ui.keyCode.ENTER:
                e.preventDefault();
                e.stopPropagation();
                break;
            }
        },
        'blur .o_grid_input': function (e) {
            var $target = $(e.target);

            var data = this.get('grid_data');
            // path should be [path, to, grid, 'grid', row_index, col_index]
            var cell_path = $target.parent().attr('data-path').split('.');
            var grid_path = cell_path.slice(0, -3);
            var row_path = grid_path.concat(['rows'], cell_path.slice(-2, -1));
            var col_path = grid_path.concat(['cols'], cell_path.slice(-1));

            try {
                var val = this._cell_field.parse(e.target.textContent.trim());
                $target.removeClass('has-error');
            } catch (_) {
                $target.addClass('has-error');
                return;
            }

            this.adjust({
                row: into(data, row_path),
                col: into(data, col_path),
                //ids: cell.ids,
                value: into(data, cell_path).value
            }, val)
        },
        'focus .o_grid_input': function (e) {
            var selection = window.getSelection();
            var range = document.createRange();
            range.selectNodeContents(e.target);
            selection.removeAllRanges();
            selection.addRange(range);
        },
        'click .btn_remove': function(e){
            var $target = $(e.target);
            var row_index = $target.data('row');
            var row_domain, stop_remove;
            var grid_data = this.get('grid_data');
            var _this = this;
            if (typeof(row_index) == "number" &&  grid_data.rows[row_index] && grid_data.grid[row_index] ){
                row_domain = grid_data.rows[row_index].domain;
                stop_remove = _(grid_data.grid[row_index]).some(function(el){return el.value > 0});
                if (!stop_remove){
                    if (confirm(_t("Ar tikrai norite ištrinti šią eilutę?"))){
                        $target.toggleClass('btn_remove', true);
                        return this._model.call('remove_grid_line', {
                            row_domain: row_domain,
                        }).done(function(){
                            _this._fetch();
                            $target.toggleClass('btn_remove', false);
                        });
                    }
                }
                else{
                    Dialog.alert(this, _t("Negalite ištrinti šios eilutės, nes yra nenulinių įrašų."));
                }

            }

        },
        'click .o_grid_cell_information': function (e) {
            var $target = $(e.target);
            var data = this.get('grid_data');
            var cell_path = $target.parent().attr('data-path').split('.');
            var row_path = cell_path.slice(0, -3).concat(['rows'], cell_path.slice(-2, -1));
            var cell = into(data, cell_path);
            var row = into(data, row_path);

            var anchor, col = this._col_field.name();
            var additional_context = {};
            if (anchor = this.get('anchor')) {
                additional_context['default_' + col] = anchor;
            }
            //ROBO: is this acceptable in general case?
            _(row.values).each(function(v, k){
                //expected format - key: [id, name]
                if (v[0] && v[1] && typeof(v[0]) == "number") {
                    additional_context['default_'+ k] = v[0];
                }
            });
            if (cell.date){
                additional_context['default_date'] = cell.date;
            }

            var views = this.ViewManager.views;
            var group_fields = this.get('groupby').slice(_.isArray(this.get('grid_data')) ? 1 : 0);
            var label = _(group_fields).map(function (name) {
                return row.values[name][1];
            }).join(': ');
            var extended_ctx = this._model.context(additional_context);
            this.do_action({
                type: 'ir.actions.act_window',
                name: label,
                res_model: this._model.name,
                views: [
                    [views.tree_robo ? views.tree_robo && views.tree_robo.view_id : false, 'tree_robo'], //ROBO: general list view possible in the future
                    // [views.list ? views.list.view_id : false, 'list'],
                    [views.form && views.form.view_id || extended_ctx.eval().quick_create_view || false, 'form']
                ],
                domain: cell.domain,
                context: extended_ctx,
            });
        }
    },
    init: function (parent, dataset) {
        this._super.apply(this, arguments);

        this._model = dataset._model;

        this._col_field = null;
        this._cell_field = null;

        this._in_waiting = null;
        this._fetch_mutex = new utils.Mutex();
        // cells are only editable if the view is *and* an adjustment callback is configured
        this._editable_cells = this.is_action_enabled('edit') && this.fields_view.arch.attrs['adjustment'];

        this.on('change:grid_data', this, this._render);
        this.on('change:range', this, this._fetch);
        this.on('change:pagination_context', this, this._fetch);
    },
    start: function () {
        this._col_field = this._fields_of_type('col')[0];
        this._cell_field = this._fields_of_type('measure')[0];

        // this is the vroot, the first patch call will replace the DOM node
        // itself instead of patching it in-place, so we're losing delegated
        // events if the state is the root node
        this._state = document.createElement('div');
        this.el.appendChild(this._state);

        this._render();
        return $.when();
    },
    _render: function () {
        var _this = this;
        var columns, vnode, grid, totals;
        var grid_data = this.get('grid_data') || {};
        if (_.isArray(grid_data)) {
            // array of grid groups
            // get columns (check they're the same in all groups)
            if (!(_.isEmpty(grid_data) || _(grid_data).reduce(function (m, it) {
                return _.isEqual(m.cols, it.cols) && m;
            }))) {
                throw new Error(_t("The sectioned grid view can't handle groups with different columns sets"));
            }

            columns = grid_data.length ? grid_data[0].cols : [];
            var super_totals = this._compute_totals(
                _.flatten(_.pluck(grid_data, 'grid'), true));
            vnode = this._table_base(columns, super_totals.columns);
            var grid_body = vnode.children[0].children;
            for (var n = 0; n < grid_data.length; n++) {
                grid = grid_data[n];

                totals = this._compute_totals(grid.grid);
                rows = this._compute_grid_rows(
                    grid.grid || [],
                    this.get('groupby').slice(1),
                    [n, 'grid'],
                    grid.rows || [],
                    totals.rows
                );
                grid_body.push(
                    h('tbody', {class: {o_grid_section: true}}, [
                        h('tr', [
                            h('th', {attrs: {colspan: 2}}, [
                                (grid.__label || [])[1] || "\u00A0"
                            ])
                        ].concat(
                            _(columns).map(function (column, column_index) {
                                return h('td', {class: {
                                    o_grid_current: column.is_current,
                                    o_grid_holiday: column.is_holiday,
                                }}, _this._cell_field.format(
                                        totals.columns[column_index]));
                            }),
                            [h('td.o_grid_total', [
                                _this._cell_field.format(totals.super)
                            ])]
                        ))
                    ].concat(rows)
                ));
            }
        } else {
            columns = grid_data.cols || [];
            var rows = grid_data.rows || [];
            grid = grid_data.grid || [];
            var group_fields = this.get('groupby');

            totals = this._compute_totals(grid);
            vnode = this._table_base(columns, totals.columns, totals.super, !grid.length);
            vnode.children[0].children.push(
                h('tbody',
                    this._compute_grid_rows(grid, group_fields, ['grid'], rows, totals.rows)
                    .concat(_(Math.max(5 - rows.length, 0)).times(function () {
                        return h('tr.o_grid_padding', [
                            h('th', {attrs: {colspan: '2'}}, "\u00A0")
                        ].concat(
                            _(columns).map(function (column) {
                                return h('td', {class: {o_grid_current: column.is_current, o_grid_holiday: column.is_holiday}}, []);
                            }),
                            [h('td.o_grid_total', [])]
                        ));
                    }))
                )
            );
        }

        this._state = patch(this._state, vnode);

        // need to debounce so grid can render
        setTimeout(function () {            _
            var row_headers = _this.el.querySelectorAll('tbody th:first-child div');
            //ROBO: need time for snabbdom to redraw.
            _this._state.key = Math.random(); //somehow snabbdom decides not to redraw header. Change update key to new.
            _this.$('table').tableHeadFixer({'z-index' : 50, left: 2, head: true, 'header-z-index': 50});
            _this.$('table').css({'border-collapse': 'separate'});
            //ROBO: now we need to throw scollbar bellow. Structure view_manager -> div -> o_grid_view
            //ROBO: y scroll bar updates from full to table level every time we fetch new data.
            _this.$el.css({height: '100%'});
            _this.$('.o_view_grid').css({height: '100%'});


            for (var k = 0; k < row_headers.length; k++) {
                var header = row_headers[k];
                if (header.scrollWidth > header.clientWidth) {
                    $(header).addClass('overflow');
                }
            }
        }, 0);
    },
    /**
     * Generates the header and footer for the grid's table. If
     * totals and super_total are provided they will be formatted and
     * inserted into the table footer, otherwise the cells will be left empty
     *
     * @param {Array} columns
     * @param {Object} [totals]
     * @param {Number} [super_total]
     * @param {Boolean} [empty=false]
     */
    _table_base: function (columns, totals, super_total, empty) {
        var _this = this;
        var col_field = this._col_field.name();
        return h('div.o_view_grid', [
            h('table.table.table-condensed.table-responsive.table-striped', [
                h('thead', [
                    h('tr', [
                        h('th.o_grid_title_header'),
                        h('th.o_grid_title_header'),
                    ].concat(
                        _(columns).map(function (column) {
                            return h('th', {class: {o_grid_current: column.is_current, o_grid_holiday: column.is_holiday}},
                                column.values[col_field][1]
                            );
                        }),
                        [h('th.o_grid_total', _t("Viso"))]
                    ))
                ]),
                h('tfoot', [
                    h('tr', [
                        h('td.o_grid_add_line', _this.is_action_enabled('create') ? [
                            h('button.btn.btn-sm.btn-primary.o_grid_button_add', {
                                attrs: {type: 'button'}
                            }, _this.add_label.toString())
                        ] : []),
                        h('td', totals ? _t("Viso") : [])
                    ].concat(
                        _(columns).map(function (column, column_index) {
                            var cell_content = !totals
                                ? []
                                : _this._cell_field.format(totals[column_index]);
                            return h('td', {class: {
                                o_grid_current: column.is_current,
                                o_grid_holiday: column.is_holiday,
                            }}, cell_content);
                        }),
                        [h('td', !super_total ? [] : _this._cell_field.format(super_total))]
                    ))
                ]),
            ])
        ].concat(this._empty_warning(empty)));
    },
    _empty_warning: function (empty) {
        empty = empty && _.find(this.fields_view.arch.children, function (c) {
            return c.tag === 'empty';
        });
        if (!empty || !empty.children.length || !this.is_action_enabled('create')) {
            return [];
        }
        return h('div.o_grid_nocontent_container', [
                   h('div.oe_view_nocontent oe_edit_only',
                       _(empty.children).map(function (p) {
                           var data = p.attrs.class
                                   ? {attrs: {class: p.attrs.class}}
                                   : {};
                           return h('p', data, p.children);
                       })
                   )
               ]);
    },
    _cell_is_readonly: function (cell) {
        return !this._editable_cells || cell.readonly === true;
    },
    /**
     *
     * @param {Array<Array>} grid actual grid content
     * @param {Array<String>} group_fields
     * @param {Array} path object path to `grid` from the object's grid_data
     * @param {Array} rows list of row keys
     * @param {Object} totals row-keyed totals
     * @returns {*}
     * @private
     */
    _compute_grid_rows: function (grid, group_fields, path, rows, totals) {
        var _this = this;
        var is_remove_btn = !!this.dataset.context.remove_button;
        var remove_btn_class = is_remove_btn ?'.icon-trash.btn_remove':'';
        return _(grid).map(function (row, row_index) {
            var row_values = [];
            for (var i = 0; i < group_fields.length; i++) {
                var row_field = group_fields[i];
                var value = rows[row_index].values[row_field];
                if (value) {
                    row_values.push(value);
                }
            }
            var row_key = _(row_values).map(function (v) {
                return v[0]
            }).join('|');

            return h('tr', {key: row_key}, [
                h('th', {attrs: {colspan: 2}}, [
                    h('div', _(row_values).map(function (v) {
                        return h('div', {attrs: {title: v[1]}}, v[1]);
                    })),h('span'+remove_btn_class, {attrs: {'data-row': row_index}}, [
                    ])
                ])
            ].concat(_(row).map(function (cell, cell_index) {
                return _this._render_cell(cell, path.concat([row_index, cell_index]).join('.'));
            }), [h('td.o_grid_total', _this._cell_field.format(totals[row_index]))]));
        });
    },
    _render_cell_inner: function (formatted_value, is_readonly) {
        if (is_readonly) {
            return h('div.o_grid_show', formatted_value)
        } else {
            return h('div.o_grid_input', {attrs: {contentEditable: "true"}}, formatted_value);
        }
    },
    _render_cell_content: function (cell_value, is_readonly, classmap, path) {
        return h('div', { class: classmap, attrs: {'data-path': path}}, [
            h('i.fa.fa-search-plus.o_grid_cell_information', {
                attrs: {
                    title: _t("Peržiūrėkite įrašus, kurie agreguoti šiame langelyje")
                }
            }, []),
            this._render_cell_inner(cell_value, is_readonly)
        ]);
    },
    _render_cell: function (cell, path) {
        var is_readonly = this._cell_is_readonly(cell);

         // these are "hard-set" for correct grid behaviour
        var classmap = {
            o_grid_cell_container: true,
            o_grid_cell_empty: !cell.size,
            o_grid_cell_readonly: is_readonly,
        };
        // merge in class info from the cell
        // classes may be completely absent, _.each treats that as an empty array
        _(cell.classes).each(function (cls) {
            // don't allow overwriting initial values
            if (!(cls in classmap)) {
                classmap[cls] = true;
            }
        });

        var cell_value = this._cell_field.format(cell.value);
        return h('td', {class: {o_grid_current: cell.is_current, o_grid_holiday: cell.is_holiday,o_grid_submitted: cell.submitted, o_grid_validated: cell.validated}}, [
            this._render_cell_content(cell_value, is_readonly, classmap, path)
        ]);
    },
    /**
     * @returns {{super: number, rows: {}, columns: {}}}
     */
    _compute_totals: function (grid) {
        var totals = {super: 0, rows: {}, columns: {}};
        for (var i = 0; i < grid.length; i++) {
            var row = grid[i];
            for (var j = 0; j < row.length; j++) {
                var cell = row[j];

                totals.super += cell.value;
                totals.rows[i] = (totals.rows[i] || 0) + cell.value;
                totals.columns[j] = (totals.columns[j] || 0) + cell.value;
            }
        }
        return totals;
    },
    do_show: function() {
        this.do_push_state({});
        return this._super();
    },
    get_ids: function () {
        var data = this.get('grid_data');
        if (!_.isArray(data)) {
            data = [data];
        }

        var domain = [];
        // count number of non-empty cells and only add those to the search
        // domain, on sparse grids this makes domains way smaller
        var cells = 0;

        for (var i = 0; i < data.length; i++) {
            var grid = data[i].grid;

            for (var j = 0; j < grid.length; j++) {
                var row = grid[j];
                for (var k = 0; k < row.length; k++) {
                    var cell = row[k];
                    if (cell.size != 0) {
                        cells++;
                        domain.push.apply(domain, cell.domain);
                    }
                }
            }
        }

        // if there are no elements in the grid we'll get an empty domain
        // which will select all records of the model... that is *not* what
        // we want
        if (cells === 0) {
            return $.when([]);
        }

        while (--cells > 0) {
            domain.unshift('|');
        }

        return this._model.call('search', [domain], {context: this.get_full_context()})
    },
    get_full_context: function (ctx) {
        var c = this._model.context(this.get('context'));
        if (this.get('pagination_context')) {
            c.add(this.get('pagination_context'));
        }
        // probably not ideal, needs to be kept in sync with arrows
        if (this.get('range')) {
            c.add({'grid_range': this.get('range')});
        }
        if (ctx) {
            c.add(ctx);
        }
        return c;
    },

    do_search: function (domain, context, groupby) {
        this.set({
            'domain': domain,
            'context': context,
            'groupby': (groupby && groupby.length)
                ? groupby
                : this._archnodes_of_type('row').map(function (node) {
                      return node.attrs.name;
                  })
        });
        return this._fetch();
    },
    _fetch_section_grid: function (section_name, section_group, additional_context) {
        return this._model.call('read_grid', {
            row_fields: this.get('groupby').slice(1),
            col_field: this._col_field.name(),
            cell_field: this._cell_field.name(),
            col_range: this.get('range') || false,
            domain: section_group.__domain,
            context: this.get_full_context(additional_context),
        }).done(function (grid) {
            grid.__label = section_group[section_name];
        });
    },
    _fetch: function () {
        // ignore if view hasn't been loaded yet
        if (!this.fields_view || this.get('range') === undefined) {
            return;
        }
        var _this = this;
        var first_field = _this.get('groupby')[0];
        var section = _(this.fields_view.arch.children).find(function (c) {
            return c.tag === 'field'
                && c.attrs.name === first_field
                && c.attrs.type === 'row'
                && c.attrs.section === '1';
        });

        // FIXME: since enqueue can drop functions, what should the semantics be for it to return a promise?
        this._enqueue(function () {
            if (section) {
                var section_name = section.attrs.name;

                return _this._model.call('read_grid_domain', {
                    field: _this._col_field.name(),
                    col_range: _this.get('range') || false,
                    context: _this.get_full_context(),
                }).then(function (d) {
                    return _this._model.call('read_group', {
                        domain: d.concat(_this.get('domain') || []),
                        fields: [section_name],
                        groupby: [section_name],
                        context: _this.get_full_context()
                    });
                }).then(function (groups) {
                    if (!groups.length) {
                        // if there are no groups in the output we still need
                        // to fetch an empty grid so we can render the table's
                        // decoration (pagination and columns &etc) otherwise
                        // we get a completely empty grid
                        return _this._fetch_section_grid(null, {
                            __domain: _this.get('domain') || [],
                        });
                    }
                    return $.when.apply(null, _(groups).map(function (group) {
                        return _this._fetch_section_grid(section_name, group);
                    }));
                }).then(function () {
                    var results = [].slice.apply(arguments);
                    var r0 = results[0];
                    _this._navigation.set({
                        prev: r0 && r0.prev,
                        next: r0 && r0.next
                    });
                    _this.set('grid_data', results);
                });
            }

            return _this._model.call('read_grid', {
                row_fields: _this.get('groupby'),
                col_field: _this._col_field.name(),
                cell_field: _this._cell_field.name(),
                col_range: _this.get('range') || false,
                domain: _this.get('domain') || [],
                context: _this.get_full_context(),
            }).then(function (results) {
                _this._navigation.set({
                    prev: results.prev, next: results.next,
                });
                _this.set('grid_data', results);
            });
        });
    },
    _enqueue: function (fn) {
        // We only want a single fetch being performed at any time (because
        // there's really no point in performing 5 fetches concurrently just
        // because the user has just edited 5 records), utils.Mutex does that
        // fine, *however* we don't actually care about all the fetches, if
        // we're enqueuing fetch n while fetch n-1 is waiting, we can just
        // drop the older one, it's only going to delay the currently
        // useful and interesting job.
        //
        // So when requesting a fetch
        // * if there's no request waiting on the mutex (for a fetch to come
        //   back) set the new request waiting and queue up a fetch on the
        //   mutex
        // * if there is already a request waiting (and thus an enqueued fetch
        //   on the mutex) just replace the old request, so it'll get taken up
        //   by the enqueued fetch eventually
        var _this = this;
        if (this._in_waiting) {
            // if there's already a query waiting for a slot, drop it and replace
            // it by the new updated query
            this._in_waiting = fn;
        } else {
            // if there's no query waiting for a slot, add the current one and
            // enqueue a fetch job
            this._in_waiting = fn;
            this._fetch_mutex.exec(function () {
                var fn = _this._in_waiting;
                _this._in_waiting = null;

                return fn();
            })
        }

    },
    _archnodes_of_type: function (type) {
        return _.filter(this.fields_view.arch.children, function (c) {
            return c.tag === 'field' && c.attrs.type === type;
        });
    },
    _make_field: function (name, arch_f) {
        var descr = this.fields_view.fields[name];
        var Cls = fields[descr.type]
               || (arch_f && fields[arch_f.attrs.widget])
               || Field;

        return new Cls(name, descr, arch_f);
    },
    _fields_of_type: function (type) {
        return _(this._archnodes_of_type(type)).map(function (arch_f) {
            var name = arch_f.attrs.name;
            return this._make_field(name, arch_f);
        }.bind(this));
    },
    render_buttons: function ($node) {
        this._navigation = new Arrows(
            this,
            this.fields_view.arch.children
                .filter(function (c) { return c.tag === 'button'; })
                .map(function (c) { return c.attrs; })
        );
        this._navigation.appendTo($node);
    },

    adjust: function (cell, new_value) {
        var difference = new_value - cell.value;
        // 1e-6 is probably an overkill, but that way milli-values are usable
        if (Math.abs(difference) < 1e-6) {
            // cell value was set to itself, don't hit the server
            return;
        }
        // convert row values to a domain, concat to action domain
        var domain = this.get('domain').concat(cell.row.domain);

        var column_name = this._col_field.name();

        return this.do_execute_action({
                type: this.fields_view.arch.attrs['adjustment'],
                name: this.fields_view.arch.attrs['adjust_name'],
                args: JSON.stringify([ // args for type=object
                    domain,
                    column_name,
                    cell.col.values[column_name][0],
                    this._cell_field.name(),
                    new_value
                    // difference
                ]),
                context: this.get_full_context({
                    'grid_adjust': { // context for type=action
                        row_domain: domain,
                        column_field: column_name,
                        column_value: cell.col.values[column_name][0],
                        cell_field: this._cell_field.name(),
                        // change: difference,
                        change: new_value,
                    }
                })
            },
            new data.DataSetStatic(null, this._model.name, {}, []), // ids=[]
            null, // record_id
            this.proxy('_fetch') // on_close
        );
    },

    get_context: function() {
        var ctx = this._super();
        if ( !('quick_create_view' in ctx) || !ctx.quick_create_view) {
            ctx.quick_create_view = this.ViewManager.views.form && this.ViewManager.views.form.view_id || false;
        }
        return ctx;
    },
});
core.view_registry.add('grid', GridView);

var Arrows = Widget.extend({
    template: 'grid.GridArrows',
    events: {
        'click .grid_arrow_previous': function (e) {
            e.stopPropagation();
            this.getParent().set('pagination_context', this.get('prev'));
        },
        'click .grid_arrow_next': function (e) {
            e.stopPropagation();
            this.getParent().set('pagination_context', this.get('next'));
        },
        'click .grid_arrow_range': function (e) {
            e.stopPropagation();
            var $target = $(e.target);
            if ($target.hasClass('active')) {
                return;
            }
            this._activate_range($target.attr('data-name'));
        },
        'click .grid_arrow_button': function (e) {
            e.stopPropagation();
            // TODO: maybe allow opting out of getting ids?
            var button = this._buttons[$(e.target).attr('data-index')];
            var parent = this.getParent();
            parent.get_ids().then(function (ids) {
                parent.do_execute_action(button, new data.DataSetStatic(
                    this,
                    parent._model.name,
                    parent.get_full_context(button.context),
                    ids
                ), undefined, parent.proxy('_fetch'));
            }.bind(this));
        }
    },
    init: function (parent, buttons) {
        this._super.apply(this, arguments);
        this._ranges = _(this.getParent()._col_field._arch.children).map(function (c) {
            return c.attrs;
        });
        this._buttons = buttons;
        this.on('change:prev', this, function (_, change) {
            this.$('.grid_arrow_previous').toggleClass('hidden', !change.newValue);
        });
        this.on('change:next', this, function (_, change) {
            this.$('.grid_arrow_next').toggleClass('hidden', !change.newValue);
        });
    },
    start: function () {
        var first_range = this._ranges[0];
        var range_name =
            this.getParent()._model.context().eval()['grid_range']
            || first_range && first_range.name;

        this._activate_range(range_name);
    },
    _activate_range: function (name) {
        var index, range = null;
        if (name) {
            index = _.findIndex(this._ranges, function (range) {
                return range.name === name;
            });
            range = index !== -1 ? this._ranges[index] : null;
        }
        this.getParent().set('range', range);

        if (!range) { return; }

        this.$('.grid_arrow_range')
                .eq(index).addClass('active')
                .siblings().removeClass('active');
    }
});
return {
    GridView: GridView,
}

});
