window.CropDuster = {};


(function($) {

	CropDuster = {

		adminMediaPrefix: '',
		staticUrl: '',
		// These are set in inline SCRIPT tags, and accessed in
		// the popup window via window.opener. They are keyed on
		// the input id.
		
		// json string of the 'sizes' attribute passed to the form field
		sizes: {},
		
		// json string of the 'auto_sizes' attribute passed to the form field
		autoSizes: {},
		
		// The default thumb. This is what is displayed in the preview box after upload.
		defaultThumbs: {},
		
		// aspect ratio of the 'sizes' attribute. float.
		aspectRatios: {},
		
		formsetPrefixes: {},
		
		minSize: {},
		
		win: null,
		
	    init: function() {
	        // Deduce adminMediaPrefix by looking at the <script>s in the
	        // current document and finding the URL of *this* module.
	        var scripts = document.getElementsByTagName('script');
	        for (var i=0; i<scripts.length; i++) {
	            if (scripts[i].src.match(/addCropDuster/)) {
	                var idx = scripts[i].src.indexOf('cropduster/js/addCropDuster');
	                CropDuster.adminMediaPrefix = scripts[i].src.substring(0, idx);
	                break;
	            }
	        }
	    },
		
		getVal: function(id, name) {
			prefix = CropDuster.formsetPrefixes[id];
			var val = $('#id_' + prefix + '-0-' + name).val();
			return (val) ? encodeURI(val) : val;
		},
		
		setVal: function(id, name, val) {
			prefix = CropDuster.formsetPrefixes[id];
			$('#id_' + prefix + '-0-' + name).val(val);
		},
		
		// open upload window
		show: function(id, href) {
			var id2=String(id).replace(/\-/g,"____").split(".").join("___");
			var imageId = $('#id_' + id).val();
			var path = CropDuster.getVal(id, 'path');
			if (imageId) {
				href += '&id=' + imageId;
			}
			if (imageId || path) {
				href += '&x=' + CropDuster.getVal(id, 'crop_x');
				href += '&y=' + CropDuster.getVal(id, 'crop_y');
				href += '&w=' + CropDuster.getVal(id, 'crop_w');
				href += '&h=' + CropDuster.getVal(id, 'crop_h');
				href += '&path=' + CropDuster.getVal(id, 'path');
			}
			href += '&image_element_id=' + encodeURI(id);
			var win = window.open(href, id2, 'height=650,width=960,resizable=yes,scrollbars=yes');
			win.focus();
			return win;
		},
		
		setThumbnails: function(id, thumbs) {
			prefix = CropDuster.formsetPrefixes[id];
			select = $('#id_' + prefix + '-0-thumbs');
			select.find('option').detach();
			for (var sizeName in thumbs) {
				var thumbId = thumbs[sizeName];
				var option = $(document.createElement('OPTION'));
				option.attr('value', thumbId);
				option.html(sizeName + ' (' + thumbId + ')');
				select.append(option);
				option.selected = true;
				option.attr('selected', 'selected');
			}
		},
		
		complete: function(id, data) {
			$('#id_' + id).val(data.id);
			CropDuster.setVal(id, 'id', data.id);
			CropDuster.setVal(id, 'crop_x', data.x);
			CropDuster.setVal(id, 'crop_y', data.y);
			CropDuster.setVal(id, 'crop_w', data.w);
			CropDuster.setVal(id, 'crop_h', data.h);
			CropDuster.setVal(id, 'path', data.path);
			CropDuster.setVal(id, '_extension', data.extension);
			prefix = CropDuster.formsetPrefixes[id];
			$('#id_' + prefix + '-TOTAL_FORMS').val('1');
			var thumbs;

			if (data.thumbs) {
				thumbs = $.parseJSON(data.thumbs);
				CropDuster.setThumbnails(id, thumbs);
			}
			if (data.thumb_urls) {
				var thumbUrls = $.parseJSON(data.thumb_urls);
				var html = '';
				var i = 0;
				for (var name in thumbUrls) {
					var url = thumbUrls[name];
					var className = "preview";
					if (i == 0) {
						className += " first";
					}
					// Append random get variable so that it refreshes
					url += '?rand=' + CropDuster.generateRandomId();
					html += '<img id="' + id + '_image_' + name + '" src="' + url + '" class="' + className + '" />';
					i++;
				}
				$('#preview_id_' + id).html(html);
			}
		},
		
		generateRandomId: function() {
			return ('000000000' + Math.ceil(Math.random()*1000000000).toString()).slice(-9);
		}
	};
	
	CropDuster.init();
	
	$(document).ready(function(){
		$('.cropduster-form span.delete input').change(function() {
			form = $(this).parents('.cropduster-form');
			if (this.checked) {
				form.addClass('pre-delete');
			} else {
				form.removeClass('pre-delete');
			}
		});
		// Re-initialize thumbnail images. This is necessary in the event that
		// that the cropduster admin form doesn't have an image id but has thumbnails
		// (for example when a new image is uploaded and the post is saved, but there is
		// a validation error on the page)
		$('.cropduster-form .id').each(function(i, el) {
			
			if ($(el).parents('.inline-related').hasClass('empty-form')) {
				return;
			}
			
			var idName = $(el).find('input').attr('name');
			
			var matches = /^(.+)-0-id$/.exec(idName);
			if (!matches || matches.length != 2) {
				return;
			}
			
			var prefix = matches[1];
			var path = $('#id_' + prefix + '-0-path').val();
			// This is in place of a negative lookbehind. It replaces all
			// double slashes that don't follow a colon.
			
			ext = $('#id_' + prefix + '-0-_extension').val();
			var html = '';
			$('#id_' + prefix + '-0-thumbs option').each(function(i, el) {
				var name = $(el).html();
				var url = CropDuster.staticUrl + '/' + path + '/' + name + '.' + ext;
				url = url.replace(/(:)?\/+/g, function($0, $1) { return $1 ? $0 : '/'; });
				url += '?rand=' + CropDuster.generateRandomId();
				var className = 'preview';
				if (i == 0) {
					className += ' first';
				}
				html += '<img id="id_' + prefix + '0--id_image_' + name + '" src="' + url + '" class="' + className + '" />';
			});
			$('#preview_id_' + idName).html(html);
		});
	});
	
})((typeof window.django != 'undefined') ? django.jQuery : jQuery);
