(function($){

    var unknownErrorMsg = 'An unknown error occurred. Contact ' +
                          '<a href="mailto:ATMOProgrammers@theatlantic.com">' +
                          'ATMOProgrammers@theatlantic.com' +
                          '</a>';

    function updateCoords(c) {
        $('#id_thumb-crop_x').val(c.x);
        $('#id_thumb-crop_y').val(c.y);
        $('#id_thumb-crop_w').val(c.w);
        $('#id_thumb-crop_h').val(c.h);
    }

    var CropBoxClass = Class.extend({

        jcrop: null,
        error: false,
        sizes: {},

        init: function(data) {
            if (typeof data != 'object' || !data) {
                return;
            }
            if (data.sizes) {
                for (var i = 0; i < data.sizes.length; i++) {
                    var size = data.sizes[i];
                    if (size.is_auto) {
                        continue;
                    }
                    this.sizes[size.name] = size;
                }
            }
        },

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
            try {
                this.jcrop.destroy();
            } catch (e) { }

            var minSize = [0, 0];
            var aspectRatio = null;

            var thumbName = $('#id_thumb-name').val();
            if (!thumbName || !this.sizes[thumbName]) {
                return;
            }
            var size = this.sizes[thumbName];
            if (!size || typeof size != 'object') {
                return;
            }

            if (size.w && size.h) {
                aspectRatio = size.w / size.h;
            }
            minSize[0] = size.min_w || size.w || 0;
            minSize[1] = size.min_h || size.h || 0;
            $.each(size.auto || [], function(i, autoSize) {
                var min_w = autoSize.min_w || autoSize.w || 0;
                var min_h = autoSize.min_h || autoSize.h || 0;
                minSize[0] = Math.max(minSize[0], min_w);
                minSize[1] = Math.max(minSize[1], min_h);
            });

            var opts = {
                setSelect: this.getCropSelect(aspectRatio),
                aspectRatio: aspectRatio,
                onSelect: updateCoords,
                trueSize: [ this.data.orig_width, this.data.orig_height ],
                minSize: minSize
            };

            this.jcrop = $.Jcrop('#cropbox', opts);

            $('#upload-footer').hide();
            $('#crop-footer').show();
        },
        getCropSelect: function(aspectRatio) {
            var x, y, w, h;

            var imgDim = {
                width: $('#cropbox').width(),
                height: $('#cropbox').height()
            };

            var imgAspect = (imgDim.width / imgDim.height);

            if (this.data.initial) {
                // If we have initial dimensions onload
                x = this.data.x;
                y = this.data.y;
                w = this.data.width;
                h = this.data.height;
            } else if (imgAspect < aspectRatio) {
                // The uploaded image is taller than the needed aspect ratio
                x = 0;
                w = imgDim.width;
                var newHeight = imgDim.width / aspectRatio;
                y = Math.round((imgDim.height - newHeight) / 2);
                h = Math.round(newHeight);
            } else {
                // The uploaded image is wider than the needed aspect ratio
                y = 0;
                h = imgDim.height;
                var newWidth = imgDim.height * aspectRatio;
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

                var width = $('#cropbox').width();
                if (width > 1) {
                    self.onImageLoad();
                    clearInterval(interval);
                }
            }, 50);
        },

        // Save dimensions for current aspect ratio
        // to hidden input in crop form
        _setHiddenInputs: function() {
            $('#id_thumb-orig_image').val(this.data.orig_url);
            $('#cropbox').attr('src', this.data.url);
        }

    });


    $(document).ready(function(){
        var imageElementId = $('#image-element-id').val();

        var $P;
        if (window.opener) {
            $P = (typeof window.opener.django == 'object')
                   ? window.opener.django.jQuery
                   : window.opener.jQuery;
        }

        var data = {};

        if ($P) {
            data = $P('#id_' + imageElementId).data();
        }
        window.cropBox = new CropBoxClass(data);

        if (typeof data == 'object') {
            if (data.sizes) {
                $('#upload-sizes,#id_thumb-sizes').val(JSON.stringify(data.sizes));
            }
        }

        var imageId = $('#id_thumb-image_id').val();
        var origImage = $('#id_thumb-orig_image').val();

        // We already have an image, initiate a jcrop instance
        if (imageId || origImage) {
            // Mimic the data returned from a POST to the upload action
            var data = {
                initial: true,
                image_id:    parseInt(imageId, 10),
                orig_width:  parseInt($('#id_thumb-orig_w').val(), 10),
                orig_height: parseInt($('#id_thumb-orig_h').val(), 10),
                width:       parseInt($('#id_thumb-width').val(), 10),
                height:      parseInt($('#id_thumb-height').val(), 10),
                x:           parseInt($('#id_thumb-crop_x').val(), 10),
                y:           parseInt($('#id_thumb-crop_y').val(), 10),
                url: $('#cropbox').attr('src')
            };
            cropBox.onSuccess(data, 'success');
        }

        $('#upload').ajaxForm({
          dataType: 'json',
          url: $('#upload').attr('action'),
          success: function(data, responseType) {
            cropBox.onSuccess(data, responseType);
          }
        });

        $('#crop-form').ajaxForm({
            dataType: 'json',
            success: function(data, responseType) {
                if (responseType == 'success') {
                    if (data.error) {
                        $('#error-container').find('.errornote').html(data.error);
                        $('#error-container').show();
                    } else {
                        $('#error-container').hide();
                        window.opener.CropDuster.complete(imageElementId, data);
                        window.close();
                    }
                }
            }
        });

        window.uploadSubmit = function() {
            $('#upload').ajaxSubmit({
              dataType: 'json',
              url: $('#upload').attr('action'),
              success: function(data, responseType) {
                cropBox.onSuccess(data, responseType);
              }
            });
            return false;
        };
    });


}(django.jQuery));