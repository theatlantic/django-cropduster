(function($){

	var imageElementId;

	var unknownErrorMsg = 'An unknown error occurred. Contact ' +
	                      '<a href="mailto:ATMOProgrammers@theatlantic.com">' +
	                      'ATMOProgrammers@theatlantic.com' +
	                      '</a>';
	
	function updateCoords(c) {
		$('#x').val(c.x);
		$('#y').val(c.y);
		$('#w').val(c.w);
		$('#h').val(c.h);
	}

	var CropBoxClass = Class.extend({

		jcrop: null,

		aspectRatio: null,

		error: false,

		minSize: [0, 0],

		onSuccess: function(data, responseType) {
			var error = false;
			if (responseType != 'success') {
				error = unknownErrorMsg;
			} else if (data.error) {
				error = data.error;
			} else if (!data.url) {
				error = unknownErrorMsg;
			}
			
			if (error) {
				$('#error-container').find('.errornote').html(error);
				$('#error-container').show();
			} else {
				$('#error-container').hide();
				this.data = data;
				
				if (!data.initial) {
					this._setHiddenInputs();
				}
				
				this._waitForImageLoad();
			}
		},
		onImageLoad: function() {
			
			if (window.opener.CropDuster.aspectRatios) {
				this.aspectRatio = window.opener.CropDuster.aspectRatios[imageElementId];
			}


			try {
				this.jcrop.destroy();
			} catch (e) { }
			
			
			this.jcrop = $.Jcrop('#cropbox img', {
				setSelect: this.getCropSelect(),
				aspectRatio: this.aspectRatio,
				onSelect: updateCoords,
				trueSize: [ this.data.orig_width, this.data.orig_height ],
				minSize: this.minSize
			});

			$('#upload-footer').hide();
			$('#crop-footer').show();
		},
		getCropSelect: function() {
			var x, y, w, h;

			var imgDim = {
				width: $('#cropbox img').width(),
				height: $('#cropbox img').height()
			};

			var imgAspect = (imgDim.width / imgDim.height);

			if (this.data.initial) {
				// If we have initial dimensions onload
				x = this.data.x;
				y = this.data.y;
				w = this.data.width;
				h = this.data.height;
			} else if (imgAspect < this.aspectRatio) {
				// The uploaded image is taller than the needed aspect ratio
				x = 0;
				w = imgDim.width;
				var newHeight = imgDim.width / this.aspectRatio;
				y = Math.round((imgDim.height - newHeight) / 2);
				h = Math.round(newHeight);
			} else {
				// The uploaded image is wider than the needed aspect ratio
				y = 0;
				h = imgDim.height;
				var newWidth = imgDim.height * this.aspectRatio;
				x = Math.round((imgDim.width - newWidth) / 2);
				w = Math.round(newWidth);
			}
			
			var scalex = imgDim.width  / this.data.orig_width;
			var scaley = imgDim.height / this.data.orig_height;
			
			if (this.data.initial) {
				// setSelect autoscales the x, y, w, and h that it feeds the
				// function, so we need to scale our data to mimic this effect
				w = Math.round((w + x) * scalex);
				h = Math.round((h + y) * scaley);
				x = Math.round(x * scalex);
				y = Math.round(y * scaley);
				// Our data is no longer initial
				this.data.initial = false;
			} else {
				// Update the hidden inputs with our best-guess crop for the aspect ratio,
				// dividing by the scale factor so that the coordinates are relative to the
				// original image
				updateCoords({
					x:  Math.round(x / scalex),
					y:  Math.round(y / scaley),
					w:  Math.round(w / scalex),
					h:  Math.round(h / scaley)
				});
			}
			return [x, y, w, h];
		},
		_waitForImageLoad: function() {
			var i = 0;
			var self = this;
			var interval = window.setInterval(function() {
				if (++i > 20) {
					// Take a break
					setTimeout(function() {
						self._waitForImageLoad();
					}, 1000);
					clearInterval(interval);
				}

				var width = $('#cropbox img').width();
				if (width > 1) {
					self.onImageLoad();
					clearInterval(interval);
				}
			}, 50);
		},
		
		// Save dimensions for current aspect ratio
		// to hidden input in crop form
		_setHiddenInputs: function() {
			$('#crop-uploaded-image').val(this.data.url);
			$('#crop-orig-image').val(this.data.orig_url);
			
			$('#cropbox img').attr('src', this.data.url);
		}
		
	});

	window.cropBox = new CropBoxClass();

}(django.jQuery));