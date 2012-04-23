$(function () {
    register_widgets("");
});
function popup_block(id) {
    $("#" + id + ".popup-background").css("display", "table");
}
function close_popup(id) {
    $("#" + id + ".popup-background").css("display", "none");
}
function register_widgets(container) {
    $(container + " .modebutton > span").click(function(object) {
        $(this).parent().children("span").removeClass("active");
        $(this).addClass("active");
    });
    $(container + " .staticnotebook > .modebutton > span").click(function(object) {
        /* Hide all the panes */
        $(this).parent().parent().children(".static-frame").hide();
        $(this).parent().parent().children(".static-" + $(this).parent().children().index($(this))).show();
    });
}
