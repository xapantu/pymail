
var list_selected = -1;
var sidebar_view = false;
var ROOTITEM_SELECTED = -1;

var VIEW_MODE = false;

function show_progress() {
    if($("body").hasClass("email")) {
        $(".hiddenbottom").animate({"right": "0em"}, 200);
    }
    else {
        $(".hiddenbottom").animate({"margin-top": "-4em"}, 200);
    }
}
function hide_progress() {
    if($("body").hasClass("email")) {
        $(".hiddenbottom").animate({"right": "-17em"}, 200);
    }
    else {
        $(".hiddenbottom").animate({"margin-top": "0em"}, 200);
    }
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
    $("#feed-" + ROOTITEM_SELECTED).removeClass("selected");
    ROOTITEM_SELECTED = id;
    $("#feed-" + id).addClass("selected");
    t = setTimeout('$("#subitems-block").html("<img src=\'/static/loading.gif\' class=\'loading\' />"); }', 100);
    if(VIEW_MODE) {
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
