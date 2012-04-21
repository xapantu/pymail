
var list_selected = -1;
var sidebar_view = false;
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

function load_subitems(id, target) {
    $.getJSON(target, {}, function(data) {
            $("#subitems-block").html(data.content);
    });
}
