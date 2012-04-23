
var list_selected = -1;
var sidebar_view = false;
var rootitem_selected = -1;
var view_normal = false;
function show_progress() {
    $(".hiddenbottom").animate({"margin-top": "-4em"}, 200);
}
function hide_progress() {
    $(".hiddenbottom").animate({"margin-top": "0em"}, 200);
}
function set_progress_text(content) {
    $("#progresstext").text(content);
}
function load_sidebar(id, target) {
    if(list_selected  != -1)
        $("#entry-" + list_selected).removeClass("selected");
    if(!sidebar_view) {
        $("#sidebar").css({width:"50%"});
        $("#content").css({width:"50%"});
    }
    sidebar_view = true;
    list_selected = id;
    $.getJSON(target, {}, function(data) {
            $("#entry-" + id).removeClass("unread");
            $("#entry-" + list_selected).addClass("selected");
            $("#sidebar").html(data.content);
            hide_progress();
    });
}
function hide_sidebar() {
    $("#sidebar").css({width:"0%"});
    $("#content").css({width:"100%"});
}

function load_subitems(id, target_normal, additional_target) {
    $("#feed-" + rootitem_selected).removeClass("selected");
    rootitem_selected = id;
    $("#feed-" + id).addClass("selected");
    t = setTimeout('$("#subitems-block").html("<img src=\'/static/loading.gif\' class=\'loading\' />"); }', 100);
    if(view_normal) {
        $.getJSON(target_normal, {}, function(data) {
            clearTimeout(t);
            $("#subitems-block").html(data.content);
        });
    }
    else {
        $.getJSON(additional_target, {}, function(data) {
            clearTimeout(t);
            $("#subitems-block").html(data.content);
        });
    }
}

function mark_as_read(id, feedid) {
    ping_url('/ajax/seen/' + id + '/1');
    $("#message-" + id).fadeTo('slow', .4);
    $("#message-" + id).removeClass('unread');
    $("#message-" + id + " .mark-read").hide();
    $("#message-" + id + " .mark-unread").show();
    update_unread_count(Number($("#unread-count-" + feedid).html()) - 1, feedid);
}

function update_unread_count(count, feedid) {
    if(count > 0) {
        $("#unread-count-" + feedid).parent().show();
        $("#feed-" + feedid).addClass("unread");
    }
    else {
        $("#unread-count-" + feedid).parent().hide();
        $("#feed-" + feedid).removeClass("unread");
    }
    $("#unread-count-" + feedid).html(count);
}

function mark_as_unread(id, feedid) {
    ping_url('/ajax/seen/' + id + '/0');
    $("#message-" + id).fadeTo('slow', 1);
    $("#message-" + id).addClass('unread');
    $("#message-" + id + " .mark-read").show();
    $("#message-" + id + " .mark-unread").hide();
    update_unread_count(Number($("#unread-count-" + feedid).html()) + 1, feedid);
}

function ping_url(target) {
    $.getJSON(target, {}, null);
}
