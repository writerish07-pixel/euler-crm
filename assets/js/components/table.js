/**
 * Simple sortable / searchable / paginated table.
 */
(function (global) {
  'use strict';

  function createDataTable(mount, options) {
    options = options || {};
    var columns = options.columns || [];
    var rows = options.rows || [];
    var pageSize = options.pageSize || 25;
    var sortKey = options.sortKey || (columns[0] && columns[0].key);
    var sortDir = options.sortDir || 'asc';
    var filter = '';
    var page = 1;
    var U = global.CRM_UTIL;

    mount.innerHTML =
      '<div class="toolbar">' +
        '<input type="search" placeholder="Filter table…" data-role="filter" />' +
        '<button type="button" class="btn btn-secondary" data-role="export">Export CSV</button>' +
      '</div>' +
      '<div class="table-wrap"><table class="data"><thead></thead><tbody></tbody></table></div>' +
      '<div class="toolbar" style="justify-content:space-between;margin-top:10px;">' +
        '<span data-role="meta" style="font-size:12px;color:var(--muted);"></span>' +
        '<div style="display:flex;gap:6px;">' +
          '<button type="button" class="btn btn-secondary" data-role="prev">Prev</button>' +
          '<button type="button" class="btn btn-secondary" data-role="next">Next</button>' +
        '</div>' +
      '</div>';

    var thead = mount.querySelector('thead');
    var tbody = mount.querySelector('tbody');
    var filterEl = mount.querySelector('[data-role="filter"]');
    var meta = mount.querySelector('[data-role="meta"]');

    function filtered() {
      var list = rows.slice();
      if (filter) {
        var q = filter.toLowerCase();
        list = list.filter(function (r) {
          return columns.some(function (c) {
            return String(r[c.key] == null ? '' : r[c.key]).toLowerCase().indexOf(q) >= 0;
          });
        });
      }
      if (sortKey) {
        list.sort(function (a, b) {
          var av = a[sortKey], bv = b[sortKey];
          if (av == null) av = '';
          if (bv == null) bv = '';
          if (typeof av === 'number' && typeof bv === 'number') return sortDir === 'asc' ? av - bv : bv - av;
          av = String(av).toLowerCase(); bv = String(bv).toLowerCase();
          if (av < bv) return sortDir === 'asc' ? -1 : 1;
          if (av > bv) return sortDir === 'asc' ? 1 : -1;
          return 0;
        });
      }
      return list;
    }

    function render() {
      thead.innerHTML = '<tr>' + columns.map(function (c) {
        var arrow = c.key === sortKey ? (sortDir === 'asc' ? ' ▲' : ' ▼') : '';
        return '<th data-key="' + c.key + '" style="cursor:pointer;">' + U.escapeHtml(c.label) + arrow + '</th>';
      }).join('') + '</tr>';

      var list = filtered();
      var pages = Math.max(1, Math.ceil(list.length / pageSize));
      if (page > pages) page = pages;
      var start = (page - 1) * pageSize;
      var slice = list.slice(start, start + pageSize);

      if (!slice.length) {
        tbody.innerHTML = '<tr><td colspan="' + columns.length + '"><div class="empty">No rows</div></td></tr>';
      } else {
        tbody.innerHTML = slice.map(function (r) {
          return '<tr>' + columns.map(function (c) {
            var val = r[c.key];
            var text = c.render ? c.render(val, r) : U.escapeHtml(val == null ? '' : val);
            return '<td>' + text + '</td>';
          }).join('') + '</tr>';
        }).join('');
      }
      meta.textContent = list.length + ' row(s) · page ' + page + ' / ' + pages;
    }

    thead.addEventListener('click', function (e) {
      var th = e.target.closest('th');
      if (!th) return;
      var key = th.getAttribute('data-key');
      if (sortKey === key) sortDir = sortDir === 'asc' ? 'desc' : 'asc';
      else { sortKey = key; sortDir = 'asc'; }
      render();
    });

    filterEl.addEventListener('input', U.debounce(function () {
      filter = filterEl.value.trim();
      page = 1;
      render();
    }, 200));

    mount.querySelector('[data-role="prev"]').addEventListener('click', function () {
      if (page > 1) { page--; render(); }
    });
    mount.querySelector('[data-role="next"]').addEventListener('click', function () {
      page++; render();
    });
    mount.querySelector('[data-role="export"]').addEventListener('click', function () {
      var list = filtered();
      var csv = [columns.map(function (c) { return c.label; }).join(',')];
      list.forEach(function (r) {
        csv.push(columns.map(function (c) {
          var v = String(r[c.key] == null ? '' : r[c.key]).replace(/"/g, '""');
          return '"' + v + '"';
        }).join(','));
      });
      var blob = new Blob([csv.join('\n')], { type: 'text/csv' });
      var a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = (options.exportName || 'export') + '.csv';
      a.click();
    });

    render();
    return {
      setRows: function (next) { rows = next || []; page = 1; render(); },
      refresh: render
    };
  }

  global.CRM_TABLE = { create: createDataTable };
})(window);
