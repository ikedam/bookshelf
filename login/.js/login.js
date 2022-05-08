$(function() {
  var form = $('#login-form');
  var focus = 'user';
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
      if (focus === 'user') {
        focus = 'password';
      }
    }
    if (params['password']) {
      $('#login-form input[name="password"]').val(params['password']);
      if (focus === 'password') {
        focus = 'submit';
      }
    }
  }
  form.submit(function(e) {
    $.ajax({
      'url': '/rpc/login',
      'type': 'POST',
      'data': form.serialize(),
      'xhrFields': {
        'withCredentials': true
      }
    }).done(function() {
      window.location.href = '/rpc/cat/scan/epub/index.html';
    });
    e.preventDefault();
  });
  $('body').append(
    $('<dl>').addClass('browser-info')
        .append($('<dt>').text('platform'))
        .append($('<dd>').text(window.navigator.platform))
        .append($('<dt>').text('userAgent'))
        .append($('<dd>').text(window.navigator.userAgent))
        .append($('<dt>').text('product'))
        .append($('<dd>').text(window.navigator.product))
        .append($('<dt>').text('appName'))
        .append($('<dd>').text(window.navigator.appName))
        .append($('<dt>').text('appVersion'))
        .append($('<dd>').text(window.navigator.appVersion))
        .append($('<dt>').text('appCodeName'))
        .append($('<dd>').text(window.navigator.appCodeName))
  );
  // Prevent Kobo displaying the keyboard when there're enabled input fields.
  $('#login-form input[name="user"]').prop('disabled', false);
  $('#login-form input[name="password"]').prop('disabled', false);
  if (focus === 'user') {
    $('#login-form input[name="user"]').focus();
  } else if (focus === 'password') {
    $('#login-form input[name="password"]').focus();
  }
});
