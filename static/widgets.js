$(function () {
    $(".modebutton > span").click(function(object) {
        $(this).parent().children("span").removeClass("active");
        $(this).addClass("active");
    });
    $(".staticnotebook > .modebutton > span").click(function(object) {
        /* Hide all the panes */
        $(this).parent().parent().children(".static-frame").hide();
        $(this).parent().parent().children(".static-" + $(this).parent().children().index($(this))).show();
    });
});
function popup_block(id) {
    $("#" + id + ".popup-background").css("display", "table");
}
function close_popup(id) {
    $("#" + id + ".popup-background").css("display", "none");
}
