(function($){

    var unknownErrorMsg = 'An unknown error occurred. Contact ' +
                          '<a href="mailto:ATMOProgrammers@theatlantic.com">' +
                          'ATMOProgrammers@theatlantic.com' +
                          '</a>';

    var ProgressBarClass = Class.extend({
        init: function() {
            this.id = CropDuster.generateRandomId();
            $('#X-Progress-ID').val(this.id);
        },
        show: function() {
            $('#progressbar-container').html('<div id="uploadprogressbar"></div>');
            $('#progressbar-container').find('#uploadprogressbar').progressbar();
            this.startUpdate();
        },
        startUpdate: function() {
            $("#uploadprogressbar").fadeIn();
            if(typeof progressInterval !== 'undefined') {
                try {
                    $("#uploadprogressbar").progressbar("destroy");
                } catch (e) { }
                clearInterval(progressInterval);
                $("#progress-wrapper").hide();
            }

            $("#progress-wrapper").show();

            var uploadId = this.id;

            progressInterval = setInterval(function() {
                var url = $('#form-upload-progress').attr('action');
                var arg = (url.indexOf('?') >= 0) ? '&' : '?';
                $.getJSON(url + arg + 'X-Progress-ID=' + uploadId, function(data) {
                    if (data == null) {
                        $("#uploadprogressbar").progressbar("destroy");
                        clearInterval(progressInterval);
                        $("#progress-wrapper").hide();
                        progressInterval = undefined;
                        return;
                    }
                    var percentage = Math.floor(100 * parseInt(data.uploaded, 10) / parseInt(data.length, 10));
                    $("#uploadprogressbar").progressbar({ value: percentage });
                    $('#progress-percent').html(percentage + '%');
                });
            }, 100);
        }
    });

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

        init: function(data) {
            if (typeof data != 'object' || !data) {
                return;
            }
            if (data.aspectRatio) {
                this.aspectRatio = data.aspectRatio;
            }
            if (data.minSize) {
                this.minSize = data.minSize;
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

            var imgDim = {
                width: $('#cropbox').width(),
                height: $('#cropbox').height()
            };

            var scalex = imgDim.width  / this.data.orig_width;
            var scaley = imgDim.height / this.data.orig_height;

            var minSize = [0, 0];

            if (Object.prototype.toString.call(this.minSize) == '[object Array]') {
                if (this.minSize.length == 2) {
                    minSize[0] = Math.floor(this.minSize[0] * scalex);
                    minSize[1] = Math.floor(this.minSize[1] * scaley);
                }
            }

            var opts = {
                setSelect: this.getCropSelect(),
                aspectRatio: this.aspectRatio,
                onSelect: updateCoords,
                trueSize: [ this.data.orig_width, this.data.orig_height ],
                minSize: minSize
            };

            this.jcrop = $.Jcrop('#cropbox', opts);

            $('#upload-footer').hide();
            $('#crop-footer').show();
        },
        getCropSelect: function() {
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
            $('#crop-uploaded-image').val(this.data.url);
            $('#crop-orig-image').val(this.data.orig_url);
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
                $('#crop-sizes,#upload-sizes').val(JSON.stringify(data.sizes));
            }
            if (data.autoSizes) {
                $('#crop-auto-sizes,#upload-auto-sizes').val(JSON.stringify(data.autoSizes));
            }
        }

        var progressBar = new ProgressBarClass();

        var actionUrl = $('#upload').attr('action');
        var arg = (actionUrl.indexOf('?') >= 0) ? '&' : '?';

        var imageId = $('#image-id').val();
        var origImage = $('#crop-orig-image').val();
        // We already have an image, initiate a jcrop instance
        if (imageId || origImage) {
            // Mimic the data returned from a POST to the upload action
            var data = {
                initial: true,
                image_id:    parseInt(imageId, 10),
                orig_width:  parseInt($('#orig-w').val(), 10),
                orig_height: parseInt($('#orig-h').val(), 10),
                width:       parseInt($('#w').val(), 10),
                height:      parseInt($('#h').val(), 10),
                x:           parseInt($('#x').val(), 10),
                y:           parseInt($('#y').val(), 10),
                url: $('#cropbox').attr('src')
            };
            cropBox.onSuccess(data, 'success');
        }


        $('#upload').ajaxForm({
          dataType: 'json',
          url: actionUrl + arg + 'X-Progress-ID='+$('#X-Progress-ID').val(),
          beforeSubmit: function() { progressBar.show(); },
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
              url: actionUrl + arg + 'X-Progress-ID='+$('#X-Progress-ID').val(),
              beforeSubmit: function() { progressBar.show(); },
              success: function(data, responseType) {
                cropBox.onSuccess(data, responseType);
              }
            });
            return false;
        };
    });


}(django.jQuery));