$(function() {
  if (!String.prototype.startsWith) {
      Object.defineProperty(String.prototype, 'startsWith', {
          value: function(search, rawPos) {
              var pos = rawPos > 0 ? rawPos|0 : 0;
              return this.substring(pos, pos + search.length) === search;
          }
      });
  }
  if (!String.prototype.endsWith) {
    String.prototype.endsWith = function(search, this_len) {
      if (this_len === undefined || this_len > this.length) {
        this_len = this.length;
      }
      return this.substring(this_len - search.length, this_len) === search;
    };
  }

  var scrollToTop = function() {
    //location.reload();
    window.scrollTo(0, 0);
    // 以下はいずれも機能しない
    // window.scrollTo(0, 0);
    // window.scroll(0, 0);
    // window.scrollBy(0, -window.screenY);
    // window.screenY = 0;
    // document.body.scrollIntoView();
    // document.body.scrollTo(0, 0);
    // $(window).scrollTop(0);
    // $(document).scrollTop(0);
    // $('body').scrollTop(0);
    // 属性
    // window.scrollY: 常時 0
    // window.screenY: 有効な値っぽい
    // window.pageYOffset: 常時 0
    // document.scrollTop: undefined
    // document.body.scrollY: undefined
    // document.body.scrollTop: 常時 0
    // document.body.pageYOffset: undefined
    // document.body.screenY: undefined
    // document.body.scroll(0, 0);
  };

  // ディレクトリ名のパーツリスト
  var current_path = [];

  // URI エスケープされたパス → ディレクトリ名のパーツリストの作成
  var resolve_path = function(path_string, base) {
    var path = [];
    if (base) {
      for (var i = 0; i < base.length; ++i) {
        var p = base[i];
        path.push(p);
      }
    }
    if (path_string) {
      var tests = ['/index.html', '/'];
      for (var i = 0; i < tests.length; ++i) {
        var suffix = tests[i];
        if (path_string.endsWith(suffix)) {
          path_string = path_string.substr(0, path_string.length - suffix.length);
        }
      }
    }
    if (!path_string) {
      return path;
    }
    var parts = path_string.split('/');
    for (var i = 0; i < parts.length; ++i) {
      var p = parts[i];
      p = decodeURIComponent(p);
      if (p === '' || p === '.') {
        continue;
      }
      if (p === '..') {
        if (path.length > 0) {
          path.pop();
        }
        continue;
      }
      path.push(p);
    }
    return path;
  };

  // ディレクトリ名のパーツリスト → アンカーフラグメントの作成
  var build_fragment = function(path, force) {
    if (!path || path.length === 0) {
      return force  ? '#' : '';
    }
    return '#' + path.map(encodeURIComponent).join('/');
  };

  // ディレクトリ名のパーツリスト → 絶対パスの作成
  var build_url = function(path) {
    if (!path || path.length === 0) {
      return '/rpc/cat/scan/epub/index.html';
    }
    return '/rpc/cat/scan/epub/' + path.map(encodeURIComponent).join('/') + '/index.html';
  };

  var resolve_url = function(base, rel) {
    if (window.URL) {
      return new URL(rel, new URL(base, window.location.href).href).href;
    }
    var join_url = function(baseUrl, relUrl) {
      if (relUrl.indexOf('://') >= 0) {
        return relUrl;
      }
      if (relUrl.startsWith('/')) {
        var proto = baseUrl.indexOf('://');
        if (proto < 0) {
          return relUrl;
        }
        var pathPos = baseUrl.indexOf('/', proto + 3);
        if (pathPos < 0) {
          pathPos = baseUrl.length;
        }
        return baseUrl.substr(0, pathPos) + relUrl;
      }
      var proto = baseUrl.indexOf('://');
      var last = baseUrl.lastIndexOf('/');
      if (last < proto + 3) {
        last = -1;
      }
      if (last == -1) {
        return baseUrl + '/' + relUrl;
      }
      return baseUrl.substr(0, last) + '/' + relUrl;
    }
    return join_url(join_url(window.location.href, base), rel);
  }

  var showerror = function(message) {
    if (!message) {
      $('#error').addClass('none');
      return;
    }
    $('#error').removeClass('none').text(message);
  }

  var booklistbuilder = function() {
  }
  booklistbuilder.prototype.prepare= function() {
    this.table = $('<table>').append(
      $('<thead>').append(
        $('<tr>')
          .append($('<th>').text('作者名・書名')
            .addClass('sorter')
            .attr('data-sort-field', 'bookname-index')
          )
          .append($('<th>').text('日付')
            .addClass('sorter')
            .attr('data-sort-field', 'bookdate')
          )
      )
    );
    this.tbody = $('<tbody>').attr('id', 'booklist');
    this.table.append(this.tbody);
  }
  booklistbuilder.prototype.sorted = function(field, desc) {
    this.table.find('[data-sort-field="' + field + '"]').addClass(
      desc ? 'ordered-desc' : 'ordered-asc'
    );
  }
  booklistbuilder.prototype.complete = function() {
    $('#loaded').empty().append(this.table);
  }
  booklistbuilder.prototype.addFileFromIndex = function(file) {
    var tr = $('<tr>').addClass('book');
    tr.addClass('file');
    var title = file.author ?
      '[' + file.author + '] ' + file.title :
      file.title;
    var newlink = $('<a>').text(title);

    var url = '/rpc/cat/scan/epub/' + file.filename.split('/').map(encodeURIComponent).join('/');
    url = url.replace(/\.zip$/, '.mobi');
    newlink.attr('href', url);
    newlink.on('click', function() {
      newlink.addClass('downloaded');
      return true;
    });
    tr.append($('<td>').addClass('title').append(newlink));
    tr.append($('<td>').addClass('date').text(moment.unix(file.mtime).format('YYYY-MM-DD hh:mm:ss')));
    this.tbody.append(tr);
  }
  booklistbuilder.prototype.addFileFromData = function(data) {
        var tr = $('<tr>').addClass('book');
        var isDir = (data.booklink.slice(-1) == '/' || data.booklink.slice(-11) == '/index.html');
        if (isDir) {
          tr.addClass('dir');
        } else {
          tr.addClass('file');
          if (data.booklink.endsWith('.epub')) {
            tr.addClass('epub');
          } else if (data.booklink.endsWith('.mobi')) {
            tr.addClass('mobi');
          }
        }
        tr.data('bookname-index', data.nameIndex);
        tr.data('bookname', data.bookname);
        tr.data('booklink', data.booklink);
        tr.data('booktitle', data.booktitle);
        tr.data('bookauthor', data.bookauthor);
        if (data.ruby) {
            tr.data('ruby', data.ruby);
        }
        tr.data('bookdate', data.bookdate);
        var newlink = $('<a>')
          .text(data.bookname);
        if (isDir) {
          var targetPath = data.path;
          var link_fragment = build_fragment(targetPath, true);
          newlink.attr('href', link_fragment);
          newlink.data('link-to', link_fragment);
          newlink.on('click', function() {
            load($(this).data('link-to'), true);
            return false;
          });
        } else {
          newlink.attr('href', data.url);
          newlink.on('click', function() {
            newlink.addClass('downloaded');
            return true;
          });
        }
        tr.append($('<td>').addClass('title').append(newlink));
        tr.append($('<td>').addClass('date').text(moment.unix(data.bookdate).format('YYYY-MM-DD hh:mm:ss')));
        this.tbody.append(tr);
  }

  var fullindex = null;

  var load_fullsearch_latest = function() {
    document.title = '最近の本 - 書籍ファイルビューワー';

    // 最新のデータ +1m 以内のファイルのリストを作成
    var dateto = (fullindex.length > 0) ? 
      fullindex[0].mtime - 30 * 24 * 60 * 60 :
      moment().subtract(30, 'days').unix();

    var builder = new booklistbuilder();
    builder.prepare();
    builder.sorted('bookdate', true);
    for (var idx = 0; idx < fullindex.length; ++idx) {
      var file = fullindex[idx];
      if (file.mtime < dateto) {
        break;
      }
      builder.addFileFromIndex(file);
    }
    builder.complete();
  }

  var fullsearch_test = function(file, search) {
    if (file.title.indexOf(search) >= 0) {
      return true;
    }
    if (file.author && file.author.indexOf(search) >= 0) {
      return true;
    }
    for (var idx = 0; idx < file.index.length; ++idx) {
      if (file.index[idx].indexOf(search) >= 0) {
        return true;
      }
    }
    return false;
  }

  var load_fullsearch_loaded = function(search) {
    $('#fullsearch-box input').val(search);
    if (!search.replace(' ', '')) {
      load_fullsearch_latest();
      return;
    }
    document.title = '検索: ' + search + ' - 書籍ファイルビューワー';

    var builder = new booklistbuilder();
    builder.prepare();
    builder.sorted('bookdate', true);
    for (var idx = 0; idx < fullindex.length; ++idx) {
      var file = fullindex[idx];
      if (!fullsearch_test(file, search)) {
        continue;
      }
      builder.addFileFromIndex(file);
    }
    builder.complete();
  }

  var load_fullsearch = function(search) {
    if (fullindex) {
      load_fullsearch_loaded(search);
      return;
    }
    var url = '/rpc/cat/scan/epub/index.json';
    $.ajax({
      'url': url,
      'dataType': 'json',
      'xhrFields': {
        'withCredentials': true
      },
    }).done(function(data) {
      fullindex = data;
      load_fullsearch_loaded(search);
    }).fail(function(jqXHR, textStatus, errorThrown) {
        if (jqXHR.status === 404) {
            // 認証ができていない場合、404 扱いになる
            $('body').addClass('unauthorized');
        }
    });
  };

  var load = function(target_fragment, doScroll) {
    if (target_fragment != null) {
      if (target_fragment) {
        target_fragment = target_fragment.substr(1);
      }
      current_path = resolve_path(target_fragment);
    }
    $('body').removeClass('fullsearch');
    var fragment = build_fragment(current_path);
    var url = build_url(current_path);
    window.location.hash = fragment;
    if (doScroll) {
      // Kindle whitepaper がスクロールをトップに持っていけないので
      // ページをリロードすることでトップに移動する。
      window.location.reload();
    }
    if (current_path.length > 0 && current_path[0] === 'fullsearch') {
      $('body').addClass('fullsearch');
      load_fullsearch(current_path.slice(1).join('/'));
      return;
    }
    document.title = (
      current_path.length > 0
      ? current_path.join('/') + ' - 書籍ファイルビューワー'
      : '書籍ファイルビューワー'
    );
    $.ajax({
      'url': url,
      'dataType': 'text',
      'xhrFields': {
        'withCredentials': true
      },
    }).done(function(data) {
      // Kindlewhitepaper で正しく処理ができないようなので、body の中身だけに絞る 
      data = data.replace(new RegExp('[\n\r]', 'g'), '');
      data = data.replace(new RegExp('^.*<body>'), '');
      data = data.replace(new RegExp('</body>.*$'), '');

      var builder = new booklistbuilder();
      builder.prepare();
      builder.sorted('bookname-index');
      var nameIndex = 1;
      var authorTitleReg = new RegExp('^\\[([^\\]]+)\\]\\s*(.*?)\\s*(?:\\(\\d+\\))?$');
      $(data).find('ul').addBack('ul').find('li a').each(function() {
        var link = $(this);
        var booklink = link.attr('href');
        var bookname = link.text();
        var booktitle = bookname;
        var bookauthor = '';
        var ruby = link.attr('ruby');
        var match = authorTitleReg.exec(bookname);
        if (match) {
          bookauthor = match[1];
          booktitle = match[2];
        }
        var bookdate = parseInt(link.attr('bookdate'));
        builder.addFileFromData({
          'booklink': booklink,
          'bookname': bookname,
          'booktitle': booktitle,
          'bookauthor': bookauthor,
          'ruby': ruby,
          'bookdate': bookdate,
          'nameIndex': nameIndex,
          'path': resolve_path(booklink, current_path),
          'url': resolve_url(url, booklink),
        });
        nameIndex += 1;
      });
      builder.complete();
      /*
      var table = $('<table>').append(
        $('<thead>').append(
          $('<tr>')
            .append($('<th>').text('作者名・書名')
              .addClass('sorter ordered-asc')
              .data('sort-field', 'bookname-index')
            )
            .append($('<th>').text('日付')
              .addClass('sorter')
              .data('sort-field', 'bookdate')
            )
        )
      );
      var tbody = $('<tbody>').attr('id', 'booklist');
      table.append(tbody);
      var nameIndex = 1;
      var authorTitleReg = new RegExp('^\\[([^\\]]+)\\]\\s*(.*?)\\s*(?:\\(\\d+\\))?$');
      $(data).find('ul').addBack('ul').find('li a').each(function() {
        var link = $(this);
        var booklink = link.attr('href');
        var bookname = link.text();
        var booktitle = bookname;
        var bookauthor = '';
        var ruby = link.attr('ruby');
        var match = authorTitleReg.exec(bookname);
        if (match) {
          bookauthor = match[1];
          booktitle = match[2];
        }
        var bookdate = parseInt(link.attr('bookdate'));
        var tr = $('<tr>').addClass('book');
        var isDir = (booklink.slice(-1) == '/' || booklink.slice(-11) == '/index.html');
        if (isDir) {
          tr.addClass('dir');
        } else {
          tr.addClass('file');
          if (booklink.endsWith('.epub')) {
            tr.addClass('epub');
          } else if (booklink.endsWith('.mobi')) {
            tr.addClass('mobi');
          }
        }
        tr.data('bookname-index', nameIndex);
        tr.data('bookname', bookname);
        tr.data('booklink', booklink);
        tr.data('booktitle', booktitle);
        tr.data('bookauthor', bookauthor);
        if (ruby) {
            tr.data('ruby', ruby);
        }
        tr.data('bookdate', bookdate);
        nameIndex += 1;
        var newlink = $('<a>')
          .text(bookname);
        if (isDir) {
          var targetPath = resolve_path(booklink, current_path);
          var link_fragment = build_fragment(targetPath, true);
          newlink.attr('href', link_fragment);
          newlink.data('link-to', link_fragment);
          newlink.on('click', function() {
            load($(this).data('link-to'), true);
            return false;
          });
        } else {
          newlink.attr('href', resolve_url(url, booklink));
          newlink.on('click', function() {
            newlink.addClass('downloaded');
            return true;
          });
        }
        tr.append($('<td>').addClass('title').append(newlink));
        tr.append($('<td>').addClass('date').text(moment.unix(bookdate).format('YYYY-MM-DD hh:mm:ss')));
        tbody.append(tr);
      });
      $('#loaded').empty().append(table);
      */
      $('#search input').val('');
      if (doScroll) {
        scrollToTop();
      }

      // ソート機能
      $(".sorter").click(function() {
        var e = $(this);
        var field = e.data("sort-field");
        var asc = e.hasClass("ordered-desc");
        var books = $("#booklist>.book");
        books.sort(function(a, b) {
          var aMeasure = $(a).data(field);
          var bMeasure = $(b).data(field);
          if(asc) {
            return aMeasure - bMeasure;
          } else {
            return bMeasure - aMeasure;
          }
        });
        $("#booklist").append(books);
        $(".sorter").removeClass("ordered-desc").removeClass("ordered-asc");
        if (asc) {
          e.addClass("ordered-asc");
        } else {
          e.addClass("ordered-desc");
        }
      });
    }).fail(function(jqXHR, textStatus, errorThrown) {
        if (jqXHR.status === 404) {
            // 認証ができていない場合、404 扱いになる
            $('body').addClass('unauthorized');
        }
    });
  }

  $('#login-form').submit(function(e) {
    var form = $(this);
    $.ajax({
      'url': '/rpc/login',
      'type': 'POST',
      'data': form.serialize(),
      'xhrFields': {
        'withCredentials': true
      }
    }).done(function() {
      $('body').removeClass('unauthorized');
      load(null, false);
    });
    e.preventDefault();
  });

  $('.root-link').click(function() {
    load('', true);
    return false;
  });
  $('#up').click(function() {
    current_path = resolve_path('..', current_path);
    load(null, true);
    return false;
  });

  // 検索
  $('#search').submit(function(e){
    e.preventDefault();
    return false;
  });
  // どうも kobo だと最後の変換前の文字列をとってきているよう。いさか → いさka など。
  $('#search input').on("input", function(e) {
    $(this).delay(100).queue(function() {
      var val = $(this).val();
      if (!val) {
        $("#booklist .book").removeClass('filtered');
        $(this).dequeue();
        return;
      }
      $("#booklist .book").each(function() {
        var e = $(this);
        if (
          e.data("bookauthor").indexOf(val) >= 0
          || e.data("booktitle").indexOf(val) >= 0
          || (e.data("ruby") && e.data("ruby").indexOf(val) >= 0)
        ) {
          e.removeClass('filtered');
        } else {
          e.addClass('filtered');
        }
      });
      $(this).dequeue();
    });
  });

  // 全検索
  $('#fullsearch-box').submit(function(e){
    e.preventDefault();
    var val = $(this).find('input').val();
    load('#fullsearch/' + val);
    return false;
  });
  /*
  // 遅くて使い物にならない
  $('#fullsearch-box input').on("input", function(e) {
    $(this).delay(100).queue(function() {
      var val = $(this).val();
      load('#fullsearch/' + val);
      $(this).dequeue();
    });
  });
  */

  var isKobo = function() {
    return window.navigator.userAgent.indexOf('Kobo eReader') >= 0;
  };

  var isKindle = function() {
    // kindle whitepaper の判定
    // なぜか window.navigator.userAgent に Kindle の文字が出ないため、
    // 他の可能性をすべて排除して Kindle と同定する
    if (window.navigator.platform !== 'Linux armv7l') {
        return false;
    }
    if (window.navigator.userAgent.indexOf('Safari') < 0) {
        return false;
    }
    return true;
  };

  if (isKobo()) {
    $('body').addClass('kobo');
  } else if (isKindle()) {
    $('body').addClass('kindle');
  } else {
    $('body').addClass('pc');
  }


  if (window.location.search) {
    var params = {};
    var pairs = window.location.search.substr(1).split('&');
    for (var i = 0; i < pairs.length; ++i) {
      var pair = pairs[i];
      var name_val = pair.split('=');
      params[decodeURIComponent(name_val[0])] = decodeURIComponent(name_val[1]);
    }
    if (params['user']) {
      $('#login-form input[name="user"]').val(params['user']);
    }
    if (params['password']) {
      $('#login-form input[name="password"]').val(params['password']);
    }
  }

  load(window.location.hash, false);

  window.onhashchange = function() {
    load(window.location.hash, false);
  };
});
