(function($){

    var unknownErrorMsg = 'An unknown error occurred. Contact ' +
                          '<a href="mailto:ATMOProgrammers@theatlantic.com">' +
                          'ATMOProgrammers@theatlantic.com' +
                          '</a>';

    var CropBoxClass = Class.extend({
        jcrop: undefined,
        data: {},
        index: 0,
        orig_w: undefined,
        orig_h: undefined,
        init: function() {},
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
        updateNav: function(i) {
            var sizeData = {};
            try {
                sizeData = $.parseJSON($('#id_thumbs-' + i + '-size').val() || '{}') || {};
            } catch(e) {}
            var thumbCount = $('.cropduster-thumb-form').length;
            if (i + 1 == thumbCount) {
              $('#nav-right').addClass('disabled');
            } else {
              $('#nav-right').removeClass('disabled');
            }
            if (i == 0) {
              $('#nav-left').addClass('disabled');
            } else {
              $('#nav-left').removeClass('disabled');
            }
            $('#crop-nav').show();
            $('#current-thumb-info').show();
            $('#current-thumb-index').html(i + 1);
            $('#thumb-total-count').html(thumbCount);
            $('#current-thumb-label').html(sizeData.label || '');

        },
        onSuccess: function(data, i) {
            var sizeData = {};
            try {
                sizeData = $.parseJSON($('#id_thumbs-' + i + '-size').val() || '{}') || {};
            } catch(e) {}
            data = $.extend({}, getFormData(), data);
            if (typeof data == 'object' && typeof data.crop == 'object' && data.crop) {
                this.orig_w = data.crop.orig_w;
                this.orig_h = data.crop.orig_h;
            }

            this.index = i;
            this.data = $.extend({}, this.data, data);

            this.updateNav(i);

            if (data.orig_url && $('#id_crop-orig_image').val() != data.orig_url) {
                $('#id_crop-orig_image').val(data.orig_url);
            }
            if (data.url) {
                if (this.jcrop) {
                    this.jcrop.destroy();
                    this.jcrop = undefined;
                }
                // 0x0 gif
                $('#cropbox').attr('src', 'data:image/gif;base64,R0lGODlhAQABAAAAACH5BAEKAAEALAAAAAABAAEAAAICTAEAOw==');
                $('#cropbox').attr('src', data.url);
                this._waitForImageLoad();
            } else if (this.jcrop && sizeData) {
                this.setCropOptions(sizeData);
            }
        },
        setCropOptions: function(size) {
            if (!size || typeof size != 'object') {
                return;
            }
            var aspectRatio = (size.w && size.h) ? (size.w / size.h) : 0;
            var minSize = [size.min_w || size.w || 0, size.min_h || size.h || 0];
            $.each(size.auto || [], function(i, autoSize) {
                var min_w = autoSize.min_w || autoSize.w || 0;
                var min_h = autoSize.min_h || autoSize.h || 0;
                minSize[0] = Math.max(minSize[0], min_w);
                minSize[1] = Math.max(minSize[1], min_h);
            });
            var options = {
                aspectRatio: aspectRatio,
                boxWidth: $('#cropbox').width(),
                boxHeight: $('#cropbox').height(),
                minSize: minSize,
                trueSize: [this.orig_w, this.orig_h],
                setSelect: this.getCropSelect(aspectRatio)
            };
            if (this.jcrop) {
                this.jcrop.setOptions(options);
            } else {
                var self = this;
                options = $.extend(options, {
                    onSelect: function(c) { self.updateCoordinates(c, self.index); }
                });
                $('#cropbox').Jcrop(options, function() {
                    self.jcrop = this;
                });
            }
        },
        onImageLoad: function() {
            this.index = 0;
            var sizeData = $.parseJSON($('#id_thumbs-0-size').val() || '{}');
            this.setCropOptions(sizeData);
            $('#upload-footer').hide();
            $('#crop-footer').show();
        },
        getCropSelect: function(aspectRatio) {
            var x, y, w, h;
            var thumbData = ($.isArray(this.data.thumbs)) ? this.data.thumbs[this.index] : {};
            if (typeof thumbData == 'object' && thumbData.crop_w && thumbData.crop_h) {
                x = parseInt(thumbData.crop_x, 10);
                y = parseInt(thumbData.crop_y, 10);
                w = parseInt(thumbData.crop_w, 10);
                h = parseInt(thumbData.crop_h, 10);
                return [x, y, x + w, y + h];
            }
            if (!aspectRatio) {
                x = 0;
                y = 0;
                w = this.orig_w;
                h = this.orig_h;
            } else if ((this.orig_w / this.orig_h) < aspectRatio) {
                // The uploaded image is taller than the needed aspect ratio
                x = 0;
                w = this.orig_w;
                h = Math.round(w / aspectRatio);
                y = Math.round((this.orig_h - h) / 2);
            } else {
                // The uploaded image is wider than the needed aspect ratio
                y = 0;
                h = this.orig_h;
                w = Math.round(h * aspectRatio);
                x = Math.round((this.orig_w - w) / 2);
            }
            // Update the hidden inputs with our best-guess crop for the
            // aspect ratio
            this.updateCoordinates({
                x: x,
                y: y,
                w: w,
                h: h
            }, this.index);
            return [x, y, (x + w), (y + h)];
        },
        timeout: undefined,
        _waitForImageLoad: function(i) {
            var i = i || 0;
            var self = this;
            if (this.timeout) {
                clearTimeout(this.timeout);
            }
            if ($('#cropbox').width() > 1) {
                if (self.timeout) {
                    clearTimeout(self.timeout);
                }
                self.onImageLoad();
                return;
            }
            if (++i > 20) {
                // Take a break
                this.timeout = setTimeout(self._waitForImageLoad, 1000);
            } else {
                this.timeout = setTimeout(function() {
                    self._waitForImageLoad(i);
                }, 50);
            }
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
                var $input = $('#id_thumbs-' + i + '-' + field);
                if ($input.attr('type') == 'checkbox') {
                    if (value && value != 'off' && value != 'false' && value != '0') {
                        $input.prop('checked', true);
                    } else {
                        $input.removeProp('checked');
                    }
                } else {
                    $input.val(value);
                }
            }
        }
    };

    window.getFormData = function() {
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
            var $input = $('#id_' + field.name);
            var formName = matches[1];
            var formsetNum = matches[2];
            var fieldName = matches[3];
            if (formName == 'thumbs' && typeof(formsetNum) == 'undefined') {
                return;
            }
            var value = field.value;
            if ($input.attr('type') == 'checkbox') {
                value = $input.prop('checked');
            }
            if (fieldName == 'size' || fieldName == 'sizes' || fieldName == 'thumbs') {
                try {
                    value = $.parseJSON(value);
                } catch(e) {}
            }
            if (fieldName.match(/^(width|height|crop_)/) && value.match(/^\d*?$/)) {
                value = parseInt(value, 10) || 0;
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

        window.cropBox = new CropBoxClass();

        if (typeof data == 'object') {
            if (data.sizes) {
                $('#upload-sizes,#id_crop-sizes').val(JSON.stringify(data.sizes));
            }
        }

        $('#nav-left,#nav-right').on('click', function(e) {
            var $this = $(this);
            var move = 0;
            if (!cropBox || !cropBox.jcrop) {
                return;
            }
            switch($this.attr('id')) {
                case 'nav-left':
                    if (cropBox.index <= 0) {
                        return;
                    }
                    move = -1;
                break;
                case 'nav-right':
                    if (cropBox.index + 1 >= $('.cropduster-thumb-form').length) {
                        return;
                    }
                    move = 1;
                break;
            }
            if (!move) {
                return;
            }
            var data = {};
            if ($P) {
                data = $.extend({}, $P('#id_' + imageElementId).data() || {});
            }
            data = $.extend({}, data, getFormData());
            delete data['url'];
            cropBox.onSuccess(data, cropBox.index + move);
        });

        // We already have an image, initiate a jcrop instance
        if (data.thumbs.length && (data.crop.image_id || data.crop.orig_image)) {
            // Mimic the data returned from a POST to the upload action
            cropBox.onSuccess($.extend({}, data, {
                url: $('#cropbox').attr('src')
            }), 0);
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

        var onSuccess = function(data, responseType, action) {
            var error;
            if (responseType != 'success') {
                error = unknownErrorMsg;
            } else if (data.error) {
                error = data.error;
            } else if (!data.url && !data.x && !data.crop) {
                error = unknownErrorMsg;
            }
            if (error) {
                $('#error-container').find('.errornote').html(data.error);
                $('#error-container').show();
                return;
            }
            $('#error-container').hide();

            if (action == 'upload') {
                $(':input[name^="thumbs-"]').each(function(i, input) {
                    var $input = $(input);
                    var name = $input.attr('name');
                    if (name.match(/\d\-crop_/) || name.match(/\-(width|height|thumbs)$/)) {
                        $input.val("");
                    } else if (name == 'thumbs-INITIAL_FORMS') {
                        $input.val("0");
                    }
                });
                $('#id_crop-thumbs').val("");
            }
            setFormData(data);

            var thumbCount = $('.cropduster-thumb-form').length;
            if (action == 'crop' && data.thumbs && (cropBox.index + 1) == thumbCount) {
                    window.opener.CropDuster.complete(imageElementId, data);
                    window.close();
                    return;
            }
            var index = (action == 'upload') ? 0 : cropBox.index + 1;
            data = $.extend({}, data, getFormData());
            cropBox.onSuccess(data, index);

            if (cropBox.index == thumbCount - 1) {
                $('#crop-button').val('Crop and Generate Thumbs');
            } else {
                $('#crop-button').val('Crop and Continue');
            }
            $('#crop-button').removeClass('disabled');

            if (action == 'upload') {
                $('#nav-right').addClass('disabled');
            }
        };

        $('#crop-form').ajaxForm({
            dataType: 'json',
            success: function(data, responseType) {
                onSuccess(data, responseType, 'crop');
            }
        });

        $('#upload').ajaxForm({
            dataType: 'json',
            url: $('#upload').attr('action'),
            success: function(data, responseType) {
                onSuccess(data, responseType, 'upload');
            }
        });

        window.uploadSubmit = function() {
            $('#upload').ajaxSubmit({
                dataType: 'json',
                url: $('#upload').attr('action'),
                success: function(data, responseType) {
                    onSuccess(data, responseType, 'upload');
                }
            });
            return false;
        };
    });


}(django.jQuery));