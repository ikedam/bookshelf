$(function() {
  if (!String.prototype.endsWith) {
    String.prototype.endsWith = function(search, this_len) {
      if (this_len === undefined || this_len > this.length) {
        this_len = this.length;
      }
      return this.substring(this_len - search.length, this_len) === search;
    };
  }

  /* タイトル */
  $("body").prepend(
    $("<h1>").text($("title").text())
  );
  $('h1').append($('<a>').attr('href', '../index.html').addClass('go-up'));

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

  var supportDownload = true;
  if (isKobo()) {
    $('body').addClass('kobo');
    // Kobo eReader は blob URL をサポートしない
    supportDownload = false;
  } else if (isKindle()) {
    $('body').addClass('kindle');
    // Kindle は blob URL をサポートしない
    supportDownload = false;
  } else {
    $('body').addClass('pc');
  }
  if (!supportDownload) {
    $('body').addClass('no-support-download');
  }

  /* 一覧 */
  var table = $("<table>").append(
    $("<thead>").append(
      $("<tr>")
        .append($("<th>").addClass('download-check').append(
          $("<label>").append(
            $("<input>").attr("type", "checkbox").addClass("dl-check-all").click(function() {
              var e = $(this);
              if (e.is(":checked")) {
                $(".dl-check").prop("checked", true);
              } else {
                $(".dl-check").prop("checked", false);
              }
            })
          ).append(
            $("<span>").addClass("checkbox-display")
          )
        ))
        .append($("<th>").text("作者名・書名")
          .addClass("sorter ordered-asc")
          .data("sort-field", "bookname-index")
        )
        .append($("<th>").text("日付")
          .addClass("sorter")
          .data("sort-field", "bookdate")
        )
    )
  );
  var tbody = $("<tbody>").attr("id", "booklist");
  table.append(tbody);
  var nameIndex = 1;
  var authorTitleReg = new RegExp("^\\[([^\\]]+)\\]\\s*(.*?)\\s*(?:\\(\\d+\\))?$");
  $("ul li a").each(function() {
    var link = $(this);
    var booklink = link.attr("href");
    var bookname = link.text();
    var booktitle = bookname;
    var bookauthor = "";
    var ruby = link.attr("ruby");
    var match = authorTitleReg.exec(bookname);
    if (match) {
      bookauthor = match[1];
      booktitle = match[2];
    }
    var bookdate = parseInt(link.attr("bookdate"));
    var tr = $("<tr>").addClass("book");
    var isDir = (booklink.slice(-1) == "/" || booklink.slice(-11) == "/index.html");
    if (isDir) {
      tr.addClass("dir");
    } else {
      tr.addClass("file");
      if (booklink.endsWith('.epub')) {
        tr.addClass('epub');
      } else if (booklink.endsWith('.mobi')) {
        tr.addClass('mobi');
      }
    }
    tr.data("bookname-index", nameIndex);
    tr.data("bookname", bookname);
    tr.data("booklink", booklink);
    tr.data("booktitle", booktitle);
    tr.data("bookauthor", bookauthor);
    if (ruby) {
        tr.data("ruby", ruby);
    }
    tr.data("bookdate", bookdate);
    nameIndex += 1;
    if (isDir) {
      tr.append($("<td>").addClass('download-check'));
    } else {
      tr.append($("<td>").addClass('download-check').append(
        $("<label>").append(
          $("<input>").attr("type", "checkbox").addClass("dl-check")
        ).append(
          $("<span>").addClass("checkbox-display")
        )
      ));
    }
    var newlink = $("<a>")
      .attr("href", booklink)
      .text(bookname);
    if (!isDir) {
      newlink.on('click', function() {
        newlink.addClass('downloaded');
        return true;
      });
    }
    tr.append($("<td>").addClass("title").append(newlink));
    tr.append($("<td>").addClass("date").text(moment.unix(bookdate).format('YYYY-MM-DD hh:mm:ss')));
    tbody.append(tr);
    /*
    // zip → cbz
    if (!isDir) {
      var cbz = $('<button>cbz</button>').click(function() {
        var e = $(this);
        e.prop('disabled', true);
        e.text('Downloading...');
        var cbzFile = new JSZip();
        var files = 0;
        $.ajax({
          'url': booklink,
          'dataType': 'binary'
        }).done(function(data) {
          e.text('Creating...' + files);
          JSZip.loadAsync(data).then(function(zip) {
            var promises = [];
            var cur = 0;
            zip.forEach(function(path, file) {
              cur = cur + 1;
              if (cur > 10) {
                return;
              }
              promises.push(file.async('blob').then(function(blob) {
                cbzFile.file(
                  path.substring(path.lastIndexOf('/') + 1),
                  blob
                );
                files = files + 1;
                e.text('Creating...' + files);
              }));
            });
            return $.when.apply($, promises);
          }).then(function() {
            e.text('Creating...');
            return cbzFile.generateAsync({type:"blob"});
          }).then(function(data) {
            e.prop('disabled', false);
            e.text('cbz');
            data = data.slice(0, data.size, "application/octet-stream")
            saveAs(data, bookname + '.cbz');
            return;
            var newUrl = URL.createObjectURL(data) + '#.cbz';
            var downloadLink = $('<a>');
            downloadLink.attr('href', newUrl);
            downloadLink.attr('download', bookname + '.cbz');
            downloadLink.attr('target', 'target');
            downloadLink.text(newUrl)
            e.after(downloadLink);
          });
        });
      });
      newlink.after(cbz);
    }
    */
    /*
    // zip → epub
    if (!isDir) {
      var cbz = $('<button>epub</button>').click(function() {
        var e = $(this);
        e.prop('disabled', true);
        e.text('Downloading...');
        $.ajax({
          'url': booklink.replace('.zip', '.kepub.epub'),
          'dataType': 'binary'
        }).done(function(data) {
          e.prop('disabled', false);
          e.text('epub');
          data = data.slice(0, data.size, "application/epub+zip")
          saveAs(data, bookname + '.kepub.epub');
          return;
          var newUrl = URL.createObjectURL(data) + '#test.kepub.epub';
          var downloadLink = $('<a>');
          downloadLink.attr('href', newUrl);
          downloadLink.attr('download', bookname + '.kepub.epub');
          downloadLink.attr('target', 'target');
          downloadLink.text(newUrl)
          e.after(downloadLink);
        });
      });
      newlink.after(cbz);
    }
    */
  });
  $("ul").before(table);
  $("ul").remove();

  /* ソート機能 */
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

  /* 検索ボックス */
  var form = $("<form>")
    .addClass("search")
    .submit(function(e){
      e.preventDefault();
      return false;
    });
  // どうも kobo だと最後の変換前の文字列をとってきているよう。いさか → いさka など。
  form.append($("<input>").on("input", function(e) {
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
  }));
  $("h1").after(form);

  /* zip ダウンロード */
  if (supportDownload) {
    if ($(".book.file").length > 0) {
      $("thead").append(
        $("<tr>").append(
          $("<td>")
            .addClass("download-all")
            .addClass("ready")
            .attr("colspan", "3")
            .text("一括ダウンロード")
        )
      );
      $(".download-all.ready").click(function() {
        var e = $(this);
        if (!e.hasClass("ready")) {
          return;
        }
        e.removeClass("ready");
        e.empty();
        if ($(".dl-check:checked").length <= 0) {
          $(".dl-check").prop("checked", true);
          $(".dl-check-all").prop("checked", true);
        }
        var dl = $("<dl>").append($("<dt>").text("ダウンロード中..."));
        e.append(dl);
        var zipFile = new JSZip();
        var folder = zipFile.folder($("title").text());
        var promises = [];
        $(".book.file").each(function() {
          var file = $(this);
          if (!file.find(".dl-check").is(":checked")) {
            return;
          }
          var bookname = file.data("bookname");
          var booklink = file.data("booklink");
          var dd = $("<dd>").text(bookname);
          dl.append(dd);
          promises.push($.ajax({
            "url": booklink,
            "dataType": "binary"
          }).done(function(data) {
            folder.file(bookname + ".zip", data);
            dd.remove();
          }).fail(function(error) {
            dd.text("FAILED " + bookname + ": " + error);
          }));
        });
        $.when.apply($, promises).then(function() {
          var dd = $("<dd>").text("Creating zip file...");
          dl.append(dd);
          return zipFile.generateAsync({type:"blob"}, function(metadata) {
            var percent = Math.round(metadata.percent * 100) / 100;
            if(metadata.currentFile) {
              dd.text("Creating zip file..." + percent + "% (" + metadata.currentFile + ")");
            } else {
              dd.text("Creating zip file..." + percent + "%");
            }
          });
        }).then(function(data) {
          e.empty()
            .addClass("ready")
            .text("一括ダウンロード");
          saveAs(data, $("title").text() + ".zip");
        }).catch(function(error) {
          var dd = $("<dd>").text("FAILED Creating zip file: " + error);
          dl.append(dd);
        });
      })
    }
  }
});
