$(function () {
    $(".modebutton > a").click(function(object) {
        $(this).parent().children("a").removeClass("active");
        $(this).addClass("active");
    });
});
