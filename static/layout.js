
var list_selected = -1;
var sidebar_view = false;
var rootitem_selected = -1;
var view_normal = false;
function load_sidebar(id, target) {
    if(list_selected  != -1)
        $("#entry-" + list_selected).removeClass("selected");
    $("#sidebar").html("<img src='{{ url_for('static', filename='loading.gif') }}' class='loading' />");
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
            //$("#sidebar").scrollTop($("#sidebar")[0].scrollHeight);
    })
}
function hide_sidebar() {
    $("#sidebar").css({width:"0%"});
    $("#content").css({width:"100%"});
}

function load_subitems(id, target_normal, additional_target) {
    $("#feed-" + rootitem_selected).removeClass("selected");
    rootitem_selected = id;
    $("#feed-" + id).addClass("selected");
    //$("#subitems-block").html("<img src='/static/loading.gif' class='loading' />");
    if(view_normal) {
        $.getJSON(target_normal, {}, function(data) {
                $("#subitems-block").html(data.content);
        });
    }
    else {
        $.getJSON(additional_target, {}, function(data) {
                $("#subitems-block").html(data.content);
        });
    }
}
