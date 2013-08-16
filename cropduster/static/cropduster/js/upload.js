(function($){

    var unknownErrorMsg = 'An unknown error occurred. Contact ' +
                          '<a href="mailto:ATMOProgrammers@theatlantic.com">' +
                          'ATMOProgrammers@theatlantic.com' +
                          '</a>';

    var CropBoxClass = Class.extend({

        jcrop: null,
        error: false,
        sizes: {},
        data: {},
        index: 0,

        init: function(data, i) {
            if (typeof data != 'object' || !data) {
                return;
            }
            this.index = i || this.index;
            if (typeof data == 'object' && $.isArray(data.thumbs) && data.thumbs[this.index]) {
                data._thumbs = data.thumbs;
                data = $.extend({}, data, data.thumbs[this.index]);
            }
            if (typeof data == 'object' && typeof data.crop == 'object') {
                data = $.extend({}, data, data.crop);
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
        updateCoordinates: function(c, i) {
            var x = Math.round(c.x),
                y = Math.round(c.y),
                w = Math.round(c.w),
                h = Math.round(c.h);

            var options = {};
            if (this.jcrop) {
                options = this.jcrop.getOptions();
            }
            if (options.minSize) {
                if (Math.abs(w - options.minSize[0]) == 1) {
                    w = options.minSize[0];
                }
                if (Math.abs(h - options.minSize[1]) == 1) {
                    w = options.minSize[1];
                }
            }
            if (options.maxSize) {
                if (Math.abs(w - options.maxSize[0]) == 1) {
                    w = options.maxSize[0];
                }
                if (Math.abs(h - options.maxSize[1]) == 1) {
                    w = options.maxSize[1];
                }
            }
            $('#id_thumbs-' + i + '-crop_x').val(x);
            $('#id_thumbs-' + i + '-crop_y').val(y);
            $('#id_thumbs-' + i + '-crop_w').val(w);
            $('#id_thumbs-' + i + '-crop_h').val(h);
        },
        onSuccess: function(data, i, responseType) {
            var error = false;
            if (responseType != 'success') {
                error = unknownErrorMsg;
            } else if (data.error) {
                error = data.error;
            } else if (!data.url && !data.x && !data.crop) {
                error = unknownErrorMsg;
            }

            data = $.extend({}, getFormData(), data);
            if (typeof data == 'object' && $.isArray(data.thumbs) && data.thumbs[i]) {
                data._thumbs = data.thumbs;
                data = $.extend({}, data, data.thumbs[i]);
            }
            if (typeof data == 'object' && typeof data.crop == 'object') {
                data = $.extend({}, data, data.crop);
            }
            if (data.w && !data.crop_w) {
                data.crop_w = data.w;
            }
            if (data.h && !data.height) {
                data.height = data.h;
            }

            if (error) {
                $('#error-container').find('.errornote').html(error);
                $('#error-container').show();
            } else {
                $('#error-container').hide();
                this.index = i;
                this.data = $.extend({}, this.data, data);

                var currentLabel = '';
                if (typeof this.sizes[this.data.name] == 'object') {
                    currentLabel = this.sizes[this.data.name].label;
                }

                $('#current-thumb-index').html(this.index + 1);
                $('#thumb-total-count').html(this.data._thumbs.length);
                $('#current-thumb-label').html(currentLabel);

                if (!data.initial && !data.changed) {
                    this._setHiddenInputs();
                }
                if (data.url) {
                    this._waitForImageLoad();
                } else if (data.thumb_name && this.jcrop) {
                    var opts = this.getCropOptions(data.name);
                    opts['trueSize'] = [this.data.orig_w, this.data.orig_h];
                    this.jcrop.setOptions(opts);
                    var rect = this.getCropSelect(opts.aspectRatio);
                    this.jcrop.setSelect(rect);
                }
            }
        },
        getCropOptions: function(size) {
            var aspectRatio, minSize = [0, 0];
            var $cropbox = $('#cropbox');

            if (typeof size == 'string') {
                size = this.sizes[size];
            }
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
            return {
                'minSize': minSize,
                'aspectRatio': aspectRatio,
                'boxWidth': $cropbox.width(),
                'boxHeight': $cropbox.height()
            };
        },
        onImageLoad: function() {
            var self = this;
            try {
                this.jcrop.destroy();
            } catch (e) { }

            var thumbName = $('#id_crop-thumb_name').val() || '';
            var options = this.getCropOptions(thumbName);
            options = $.extend(options, {
                setSelect: this.getCropSelect(options['aspectRatio']),
                onSelect: function(c) {
                    self.updateCoordinates(c, self.index);
                },
                trueSize: [this.data.orig_w, this.data.orig_h]
            });

            $('#cropbox').Jcrop(options, function() {
                self.jcrop = this;
            });

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
            if (!aspectRatio) {
                aspectRatio = imgAspect;
            }

            if (this.data.initial) {
                // If we have initial dimensions onload
                x = this.data.crop_x;
                y = this.data.crop_y;
                w = this.data.crop_w;
                h = this.data.crop_h;
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

            var scalex = imgDim.width  / this.data.orig_w;
            var scaley = imgDim.height / this.data.orig_h;

            if (this.data.initial) {
                if (!this.jcrop) {
                    // setSelect autoscales the x, y, w, and h that it feeds the
                    // function, so we need to scale our data to mimic this effect
                    w = Math.round((w + x) * scalex);
                    h = Math.round((h + y) * scaley);
                    x = Math.round(x * scalex);
                    y = Math.round(y * scaley);
                }
                // Our data is no longer initial
                this.data.initial = false;
            } else {
                // Update the hidden inputs with our best-guess crop for the aspect ratio,
                // dividing by the scale factor so that the coordinates are relative to the
                // original image
                this.updateCoordinates({
                    x:  Math.round(x / scalex),
                    y:  Math.round(y / scaley),
                    w:  Math.round(w / scalex),
                    h:  Math.round(h / scaley)
                }, this.index);
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
            $('#id_crop-orig_image').val(this.data.orig_url);
            $('#cropbox').attr('src', this.data.url);
        }

    });

    var setFormData = function(data) {
        if (typeof data != 'object') {
            return;
        }
        var field;
        if (typeof data.crop == 'object') {
            for (field in data.crop) {
                var value = data.crop[field];
                if (Object.prototype.toString.call(value).match(/\[object (Object|Array)\]/)) {
                    value = JSON.stringify(value);
                }
                if (typeof(value) == 'object' && $.isEmptyObject(value)) {
                    value = '';
                }
                if (!value && field.match(/(sizes|orig_w|orig_h|image_id)/)) {
                    continue;
                }
                $('#id_crop-' + field).val(value);
            }
        }
        if (Object.prototype.toString.call(data.thumbs) != '[object Array]') {
            return;
        }
        for (var i = 0; i < data.thumbs.length; i++) {
            for (field in data.thumbs[i]) {
                var value = data.thumbs[i][field];
                if (Object.prototype.toString.call(value).match(/\[object (Object|Array)\]/)) {
                    value = JSON.stringify(value);
                }
                $('#id_thumbs-' + i + '-' + field).val(value);
            }
        }
    };

    var getFormData = function() {
        var fields = $(':input').serializeArray();
        var data = {
            thumbs: [],
            crop: {}
        };
        for (var i = 0; i < $('.cropduster-thumb-form').length; i++) {
            data.thumbs.push({});
        }
        $.each(fields, function(i, field) {
            if (!field.name) {
                return;
            }
            var matches = field.name.match(/^(thumbs|crop)\-(\d+)?\-?(.+)$/);
            if (!matches) {
                return;
            }
            var formName = matches[1];
            var formsetNum = matches[2];
            var fieldName = matches[3];
            if (formName == 'thumbs' && typeof(formsetNum) == 'undefined') {
                return;
            }
            var value = field.value;
            if (fieldName == 'size' || fieldName == 'sizes' || fieldName == 'thumbs') {
                try {
                    value = $.parseJSON(value);
                } catch(e) {}
            }
            if (fieldName.match(/^(width|height|crop_)/) && value.match(/^\d+$/)) {
                value = parseInt(value, 10);
            }
            if (formName == 'crop') {
                data.crop[fieldName] = value;
            } else if (formName == 'thumbs') {
                data.thumbs[formsetNum][fieldName] = value;
            }
        });
        return data;
    };

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
            data = $P('#id_' + imageElementId).data() || {};
        }
        data = $.extend({}, data, getFormData());

        window.cropBox = new CropBoxClass(data);

        if (typeof data == 'object') {
            if (data.sizes) {
                $('#upload-sizes,#id_crop-sizes').val(JSON.stringify(data.sizes));
            }
        }

        // We already have an image, initiate a jcrop instance
        if (data.thumbs.length && (data.crop.image_id || data.crop.orig_image)) {
            // Mimic the data returned from a POST to the upload action
            cropBox.onSuccess($.extend({}, data, {
                initial: true,
                url: $('#cropbox').attr('src')
            }), 0, 'success');
        } else {
            // We don't have initial data, disable the crop button
            $('#crop-button').addClass('disabled');
            $('#upload-footer').show();
            $('#crop-footer').hide();
        }

        // Don't propagate clicks on disabled buttons
        $(document.body).on('click', 'input[type="submit"].disabled', function(e) {
            e.preventDefault();
            e.stopPropagation();
            return false;
        });

        // Enable upload and reupload buttons after the user has picked a file
        $('#picture').on('change', function(e) {
            var $input = $(this);
            if ($input.val()) {
                $('#upload-button,#reupload-button').removeClass('disabled');
            } else {
                $('#upload-button,#reupload-button').addClass('disabled');
            }
        });



        var uploadSuccess = function(data, responseType, action) {

            if (responseType == 'success') {
                if (data.error) {
                    $('#error-container').find('.errornote').html(data.error);
                    $('#error-container').show();
                } else {
                    $('#error-container').hide();
                    setFormData(data);

                    if (action == 'upload') {
                        $(':input[name^="thumbs-"]').filter(
                            '[name*="crop_"],[name$="-id"],[name$="-width"],[name$="-height"],[name$="-thumbs"]').val("");
                        $('#id_thumbs-INITIAL_FORMS').val(0);
                    }

                    var thumbCount = $('.cropduster-thumb-form').length;

                    var index = (action == 'upload') ? 0 : cropBox.index + 1;
                    if (data.thumbs && index == thumbCount && action == 'crop') {
                        window.opener.CropDuster.complete(imageElementId, data);
                        window.close();
                        return;
                    }
                    cropBox.onSuccess(data, index, responseType);

                    if (cropBox.data._thumbs && cropBox.index == thumbCount - 1) {
                        $('#crop-button').val('Crop and Generate Thumbs');
                    } else {
                        $('#crop-button').val('Crop and Continue');
                    }
                    if (data.thumbs && cropBox.index == thumbCount && action == 'crop') {
                        cropBox.
                        window.opener.CropDuster.complete(imageElementId, data);
                        window.close();
                    }
                    $('#crop-button').removeClass('disabled');
                }
            }
        };
        $('#crop-form').ajaxForm({
            dataType: 'json',
            success: function(data, responseType) {
                uploadSuccess(data, responseType, 'crop');
            }
        });

        $('#upload').ajaxForm({
            dataType: 'json',
            url: $('#upload').attr('action'),
            success: function(data, responseType) {
                uploadSuccess(data, responseType, 'upload');
            }
        });

        window.uploadSubmit = function() {
            $('#upload').ajaxSubmit({
                dataType: 'json',
                url: $('#upload').attr('action'),
                success: function(data, responseType) {
                    uploadSuccess(data, responseType, 'upload');
                }
            });
            return false;
        };
    });


}(django.jQuery));