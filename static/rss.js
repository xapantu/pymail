function mark_all_read() {
    ping_url('/ajax/seen/feed/' + ROOTITEM_SELECTED + '/1');
    if(!VIEW_MODE) {
        $(".message").fadeTo('slow', .4);
        $(".message").removeClass('unread');
        $(".mark-read").hide();
        $(".mark-unread").show();
    }
    if(ROOTITEM_SELECTED != -1) {
        update_unread_count(0, ROOTITEM_SELECTED);
    }
    else {
        $(".unread-count").parent().hide();
        $(".feed").removeClass("unread");
    }
}

function mark_as_read(id, feedid) {
    ping_url('/ajax/seen/' + id + '/1');
    if(!VIEW_MODE) {
        $("#message-" + id).fadeTo('slow', .4);
        $("#message-" + id).removeClass('unread');
        $("#message-" + id + " .mark-read").hide();
        $("#message-" + id + " .mark-unread").show();
    }
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
    if(!VIEW_MODE) {
        $("#message-" + id).fadeTo('slow', 1);
        $("#message-" + id).addClass('unread');
        $("#message-" + id + " .mark-read").show();
        $("#message-" + id + " .mark-unread").hide();
    }
    update_unread_count(Number($("#unread-count-" + feedid).html()) + 1, feedid);
}

function add_feed() {
    $("#popup-block-content").html('<form method="POST" action"/">'
            + '<input type="text" name="new_feed" placeholder="Feed URI..." class="entry" />'
            + '<input type="submit" value="Add" /></form>');
    $("#popup-block-header").html("Add a feed");
    $("#popup-background").show();
}
function close_popup() {
    $("#popup-background").hide();
}
function sync_all_rss() {
    set_progress_text("Syncing with remote servers...");
    show_progress();
    $("#sync-button").addClass("insensitive");
            if ("WebSocket" in window) {                                         
                ws = new WebSocket("ws://" + document.domain + ":5001/api/sync");
                ws.onmessage = function (msg) { 
                    eval("data = " + msg.data + ";");
                    if(data.done == undefined)
                        set_progress_text("Syncing " + data.message + "...");
                    else {
                        ws.send("close");
                        hide_progress();
                        $("#sync-button").removeClass("insensitive");
                        load_subitems(ROOTITEM_SELECTED, '/ajax/feed/' + ROOTITEM_SELECTED, '/ajax/fullview/' + ROOTITEM_SELECTED);
                    }
                };
            } else {                                                             
                alert("WebSocket not supported");
            }                                                                    
    /*$.getJSON("/sync", {}, function(data) {
        $("#rootelements").html(data.content);
        $("#sync-button").removeClass("insensitive");
        hide_progress();
        load_subitems(ROOTITEM_SELECTED, '/ajax/feed/' + ROOTITEM_SELECTED, '/ajax/fullview/' + ROOTITEM_SELECTED);
    });*/
}

/* This may be better in layout.js, needs investigation */
$(function(){
    $("#viewswitcher > *").click(function(object) {
        VIEW_MODE = $(this).attr("id") == "view1";
        $("#subitems-block").html("");
        if (VIEW_MODE) {
            $("#mainsubdiv").addClass("list");
        }
        else {
            $("#mainsubdiv").removeClass("list");
            hide_sidebar();
        }
        
        load_subitems(ROOTITEM_SELECTED, '/ajax/feed/' + ROOTITEM_SELECTED, '/ajax/fullview/' + ROOTITEM_SELECTED);
    });
    $("#viewswitcher .active").click();
});

$(function() {
    load_subitems(-1, '/ajax/feed/-1', '/ajax/fullview/-1');
});
