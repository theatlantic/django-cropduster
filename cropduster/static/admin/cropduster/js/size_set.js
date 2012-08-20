
(function($){
	$(function(){
	
		$(".width, .height").change(function(){
	
			$(this).parent().find(".aspect_ratio").css("background-color", "#ddd");
			
			var this_row = $(this).parent();
			
			
			$.get(ADMIN_URL + "cropduster/ratio/", {
				"width" : this_row.find(".width input").val(),
				"height" : this_row.find(".height input").val()
			}, function(data){
				this_row.find(".aspect_ratio p").text(eval(data)[0]);
			});
			
		});
	
	});
 }(django.jQuery));