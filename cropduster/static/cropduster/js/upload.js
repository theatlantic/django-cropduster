(function($){

    var unknownErrorMsg = 'An unknown error occurred. Contact ' +
                          '<a href="mailto:ATMOProgrammers@theatlantic.com">' +
                          'ATMOProgrammers@theatlantic.com' +
                          '</a>';

    var GET_params = (function() {
        var url = window.location.search.substr(1);
        var parts = url.split('&');
        var data = {};
        for (var i = 0; i < parts.length; i++) {
            var part = parts[i];
            var splits = part.split('=');
            if (splits.length <= 2) {
                var key = splits[0];
                var val = decodeURIComponent(splits[1] || '');
                data[key] = val;
            }
        }
        return data;
    })();

    var syncSizeForm = function() {
        if (!$('#id_standalone').is(':checked')) {
            return;
        }
        var sizes;
        try {
            sizes = JSON.parse($('#id_crop-sizes').val());
        } catch(e) {}

        var $width = $('#id_size-width');
        var $height = $('#id_size-height');

        $width.val('');
        $height.val('');

        if (typeof sizes != 'object' || !$.isArray(sizes) || sizes.length != 1) {
            return;
        }
        if (!$width.length || !$height.length) {
            return;
        }
        var size = sizes[0];

        $width.val(size.w || '');
        $height.val(size.h || '');

        var orig_w = parseInt($('#id_crop-orig_w').val(), 10) || 0;
        var orig_h = parseInt($('#id_crop-orig_h').val(), 10) || 0;

        var crop_w = parseInt($('#id_thumbs-0-crop_w').val(), 10);
        var crop_h = parseInt($('#id_thumbs-0-crop_h').val(), 10);

        if (crop_w && crop_h) {
            $('form#size').find('.row.width,.row.height').show();
        }

        var userWidth = $width.val();
        var userHeight = $height.val();

        if (size.max_w) {
            userWidth = Math.min(size.max_w, userWidth);
        }
        if (size.max_h) {
            userHeight = Math.min(size.max_h, userHeight);
        }
        if (userWidth && !userHeight && crop_w) {
            var height = Math.round((sizes[0].w / crop_w) * crop_h);
            $height.attr('placeholder', height);
        } else if (userHeight && !userWidth && crop_h) {
            var width = Math.round((sizes[0].h / crop_h) * crop_w);
            $width.attr('placeholder', width);
        } else if (!userWidth && !userHeight) {
            var max_scales = [], max_scale;
            if (crop_w && crop_h && (size.max_w && crop_w > size.max_w) || (size.max_h && crop_h > size.max_h)) {
                var crop_scales = [], crop_scale;
                if (size.max_w && size.max_w < crop_w) {
                    crop_scales.push(size.max_w / crop_w);
                }
                if (size.max_h && size.max_h < crop_h) {
                    crop_scales.push(size.max_h / crop_h);
                }
                if (crop_scales.length) {
                    crop_scale = Math.max.apply(null, crop_scales);
                    crop_w = Math.max(1, Math.round(crop_w * crop_scale));
                    crop_h = Math.max(1, Math.round(crop_h * crop_scale));
                    if (size.max_w) {
                        crop_w = Math.min(size.max_w, crop_w);
                    }
                    if (size.max_h) {
                        crop_h = Math.min(size.max_h, crop_h);
                    }
                }
            } else if (orig_w && orig_h && crop_w && crop_h) {
                if (size.max_w && size.max_w < orig_w) {
                    max_scales.push(size.max_w / orig_w);
                }
                if (size.max_h && size.max_h < orig_h) {
                    max_scales.push(size.max_h / orig_h);
                }
                if (max_scales.length) {
                    max_scale = Math.min.apply(null, max_scales);
                    crop_w = Math.max(1, Math.round(crop_w * max_scale));
                    crop_h = Math.max(1, Math.round(crop_h * max_scale));
                    if (size.max_w) {
                        crop_w = Math.min(size.max_w, crop_w);
                    }
                    if (size.max_h) {
                        crop_h = Math.min(size.max_h, crop_h);
                    }
                }
            }

            if (crop_w) {
                $width.attr('placeholder', crop_w);
            } else {
                $width.removeAttr('placeholder');
            }

            if (crop_h) {
                $height.attr('placeholder', crop_h);
            } else {
                $height.removeAttr('placeholder');
            }
        }
    };


    var calcMinSize = function calcMinSize(size) {
        var minSize = [size.min_w || size.w || 0, size.min_h || size.h || 0];
        $.each(size.auto || [], function(i, autoSize) {
            if (!autoSize.required) {
                return;
            }
            var min_w = autoSize.min_w || autoSize.w || 0;
            var min_h = autoSize.min_h || autoSize.h || 0;
            minSize[0] = Math.max(minSize[0], min_w);
            minSize[1] = Math.max(minSize[1], min_h);
        });
        return minSize;
    };
    // Fill in 'Min Size' help text
    $(document).ready(function(){
        var isStandalone = $('body').is('.cropduster-standalone');
        var sizes = JSON.parse($('#id_crop-sizes').val());
        if (isStandalone || !sizes) {
            return;
        }
        var minSizes = sizes.map(calcMinSize);
        var largest = [
            Math.max.apply(null, minSizes.map(function(s) { return s[0]; })) || 1,
            Math.max.apply(null, minSizes.map(function(s) { return s[1]; })) || 1
        ];
        $('#upload-min-size-help').html('Min. size: ' + largest.join(' x '));
    });

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
            // If the top left coordinates are outside the image, set them to 0
            if (y < 0) {
                h += y;
                y = 0;
            }
            if (x < 0) {
                w += x;
                x = 0;
            }
            if (options.minSize) {
                if (Math.abs(w - options.minSize[0]) == 1) {
                    w = options.minSize[0];
                }
                if (Math.abs(h - options.minSize[1]) == 1) {
                    h = options.minSize[1];
                }
            }
            if (options.maxSize) {
                if (Math.abs(w - options.maxSize[0]) == 1) {
                    w = options.maxSize[0];
                }
                if (Math.abs(h - options.maxSize[1]) == 1) {
                    h = options.maxSize[1];
                }
            }
            $('#id_thumbs-' + i + '-crop_x').val(x);
            $('#id_thumbs-' + i + '-crop_y').val(y);
            $('#id_thumbs-' + i + '-crop_w').val(w);
            $('#id_thumbs-' + i + '-crop_h').val(h);
            syncSizeForm();
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
            if (thumbCount == 1) {
                $('#crop-nav,#current-thumb-info').hide();
            } else {
                $('#crop-nav,#current-thumb-info').show();
                $('#current-thumb-index').html(i + 1);
                $('#thumb-total-count').html(thumbCount);
                $('#current-thumb-label').html(sizeData.label || '');
            }

        },
        onSuccess: function(data, i) {
            var sizeData = {};
            try {
                sizeData = $.parseJSON($('#id_thumbs-' + i + '-size').val() || '{}') || {};
            } catch(e) {}
            data = $.extend({}, getFormData(), data);
            if (typeof data == 'object' && typeof data.crop == 'object' && data.crop) {
                this.orig_w = parseInt(data.crop.orig_w, 10);
                this.orig_h = parseInt(data.crop.orig_h, 10);
            }

            this.index = i;
            this.data = $.extend({}, this.data, data);

            this.updateNav(i);

            if (data.orig_image && $('#id_crop-orig_image').val() != data.orig_image) {
                $('#id_crop-orig_image').val(data.orig_image);
            }
            if (data.url) {
                if (this.jcrop) {
                    this.jcrop.destroy();
                    this.jcrop = undefined;
                }
                // Reset width & height css styles to auto
                $('#cropbox').css({width: '', height: ''});
                // 0x0 gif
                $('#cropbox').attr('src', 'data:image/gif;base64,R0lGODlhAQABAAAAACH5BAEKAAEALAAAAAABAAEAAAICTAEAOw==');
                $('#cropbox').attr('src', data.url);
                this._waitForImageLoad();
            } else if (this.jcrop && sizeData) {
                this.setCropOptions(sizeData);
            }
        },
        getAspectRatioExtent: function(size) {
            var aspect = (!size.is_auto && size.w && size.h) ? (size.w / size.h) : 0,
                minAspect = aspect,
                maxAspect = aspect || Infinity;

            if (size.w && size.min_h > 1) {
                maxAspect = Math.min(maxAspect, size.w / size.min_h);
            }
            if (size.w && size.max_h) {
                minAspect = Math.max(minAspect, size.w / size.max_h);
            }
            if (size.h && size.min_w > 1) {
                minAspect = Math.max(minAspect, size.min_w / size.h);
            }
            if (size.h && size.max_w) {
                maxAspect = Math.min(maxAspect, size.max_w / size.h);
            }

            return {
                min: minAspect,
                max: maxAspect
            };
        },
        setCropOptions: function(size) {
            if (!size || typeof size != 'object') {
                return;
            }
            var self = this;

            var aspectRatio = (size.w && size.h) ? (size.w / size.h) : 0,
                minAspectRatio = aspectRatio,
                maxAspectRatio = aspectRatio || Infinity;
            var minSize = {
                w: size.min_w || size.w || 0,
                h: size.min_h || size.h || 0
            };

            var aspectExtent = this.getAspectRatioExtent(size);

            $.each(size.auto || [], function(i, autoSize) {
                minSize.w = Math.max(minSize.w, autoSize.min_w || autoSize.w || 0);
                minSize.h = Math.max(minSize.h, autoSize.min_h || autoSize.h || 0);
            });

            if (aspectExtent.max == Infinity) {
                aspectExtent.max = 0;
            }

            var options = {
                boxWidth: $('#cropbox').prop('naturalWidth'),
                boxHeight: $('#cropbox').prop('naturalHeight'),
                minSize: calcMinSize(size),
                trueSize: [this.orig_w, this.orig_h],
                setSelect: this.getCropSelect(aspectRatio, aspectExtent),
                bgColor: '#ffffff'
            };
            if (aspectRatio) {
                options.aspectRatio = aspectRatio;
            } else {
                options.minAspectRatio = aspectExtent.min;
                options.maxAspectRatio = aspectExtent.max;
            }
            if (this.jcrop) {
                this.jcrop.setOptions(options);
            } else {
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
        getCropSelect: function(aspectRatio, aspectExtent) {
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
                aspectRatio = w / h;
                if (aspectExtent.min && aspectRatio < aspectExtent.min) {
                    aspectRatio = aspectExtent.min;
                } else if (aspectExtent.max && aspectRatio > aspectExtent.max) {
                    aspectRatio = aspectExtent.max;
                }
            }
            if ((this.orig_w / this.orig_h) < aspectRatio) {
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
            if (this.timeout) {
                clearTimeout(this.timeout);
                this.timeout = undefined;
            }
            if ($('#cropbox').prop('naturalWidth') > 1) {
                this.onImageLoad();
                return;
            }
            var self = this;
            if (++i > 20) {
                // Take a break
                this.timeout = setTimeout(function() {
                    self._waitForImageLoad(0);
                }, 1000);
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
                if (!value && field.match(/(sizes|orig_w|orig_h)/)) {
                    continue;
                }
                $('#id_crop-' + field).val(value);
            }
        }
        if (Object.prototype.toString.call(data.thumbs) != '[object Array]') {
            return;
        }

        var initialFormCount = 0;

        for (var i = 0; i < data.thumbs.length; i++) {
            for (field in data.thumbs[i]) {
                var value = data.thumbs[i][field];
                if (field == 'id' && value) {
                    initialFormCount++;
                }
                if (Object.prototype.toString.call(value).match(/\[object (Object|Array)\]/)) {
                    value = JSON.stringify(value);
                }
                var $input = $('#id_thumbs-' + i + '-' + field);
                if ($input.attr('type') == 'checkbox') {
                    if (value && value != 'off' && value != 'false' && value != '0') {
                        $input[0].checked = true;
                    } else {
                        delete $input[0].checked;
                    }
                } else {
                    $input.val(value);
                }
            }
        }
        $('#id_thumbs-INITIAL_FORMS').val(initialFormCount);
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
                value = $input[0].checked;
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

    var registerStandaloneSizeHandlers = function() {
        var sizes, size;
        try {
            sizes = JSON.parse($('#id_sizes').val());
        } catch(e) {}

        if (sizes && $.isArray(sizes) && sizes.length == 1) {
            size = sizes[0];
        }

        var $inputs = $('#id_size-width,#id_size-height');

        $inputs.on('focus', function(e) {
            var $input = $(e.target);
            $input.data('originalValue', $input.val());
        });
        $inputs.on('change', function(e) {
            var $input = $(e.target);
            var originalValue = $input.data('originalValue');
            var val = $input.val();

            var sizeType = ($input.attr('id').indexOf('width') > -1) ? 'w' : 'h';

            var originalSize = parseInt($('#id_crop-orig_' + sizeType).val(), 10) || 0;
            var maxSize = (typeof size == 'object') ? size['max_' + sizeType] : undefined;

            if (val !== '0' && !val) { return; }

            val = parseInt(val, 10);

            if (val < 1) {
                $input.val(originalValue);
            }
            if (originalSize && val > originalSize) {
                $input.val(originalValue);
            }
            if (maxSize && val > maxSize) {
                $input.val(originalValue);
            }
        });
    };

    $(document).ready(function(){
        var imageElementId = $('#id_image_element_id').val();

        registerStandaloneSizeHandlers();

        var $P;
        var parent = (window.opener) ? window.opener : window.parent;
        if (parent == window) {
            parent = null;
        }
        if (parent) {
            $P = (typeof parent.django == 'object')
                ? parent.django.jQuery
                : parent.jQuery;
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

        syncSizeForm();

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
        $('#id_image').on('change', function(e) {
            var $input = $(this);
            var isStandalone = $('body').is('.cropduster-standalone');
            var $buttons = $('#upload-button,#reupload-button');
            if ($input.val()) {
                $buttons.removeClass('disabled');
                if (isStandalone) {
                    $buttons.show();
                }
            } else {
                $buttons.addClass('disabled');
                if (isStandalone) {
                    $buttons.hide();
                }
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
            var $errorContainer = $('#error-container');
            if (error) {
                $errorContainer.find('.errornote').html(data.error);
                $errorContainer.show();
                return;
            }

            $errorContainer.hide();

            var $messagelist = $errorContainer.parent().find('ul.messagelist,ul.grp-messagelist');

            if (typeof data == 'object' && $.isArray(data.warning) && data.warning.length) {
                if (!$messagelist.length) {
                    $errorContainer.after($('<ul class="messagelist grp-messagelist"><li class="warning grp-warning"></li></ul>'));
                    $messagelist = $errorContainer.parent().find('.messagelist,.grp-messagelist');
                }
                $messagelist.show();
                $messagelist.find('li.warning').html(data.warning.join('<br/>'));
            } else {
                $messagelist.hide();
            }

            if (action == 'upload') {
                $(':input[name^="thumbs-"]').each(function(i, input) {
                    var $input = $(input);
                    var name = $input.attr('name');
                    if (name.match(/\d\-crop_/) || name.match(/\-(width|height|thumbs)$/)) {
                        $input.val('');
                    } else if (name == 'thumbs-INITIAL_FORMS') {
                        $input.val('0');
                    }
                });
                $('#id_crop-thumbs').val('');
                $('#upload-button,#reupload-button').hide();
            }
            setFormData(data);
            syncSizeForm(action);

            var thumbCount = $('.cropduster-thumb-form').length;
            var parent = (window.opener) ? window.opener : window.parent;
            if (parent == window) {
                parent = null;
            }
            if (action == 'crop' && data.thumbs && (cropBox.index + 1) == thumbCount) {
                if (typeof GET_params['callback_fn'] != 'undefined') {
                    parent[GET_params.callback_fn](GET_params['callback_fn'], data);
                } else {
                    parent.CropDuster.complete(imageElementId, data);
                }
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
            beforeSubmit: function() {
                $('#crop-button').addClass('disabled').val('Cropping...');
            },
            success: function(data, responseType) {
                onSuccess(data, responseType, 'crop');
            }
        });

        window.uploadSubmit = function(element) {
            if (element && $(element).hasClass('disabled')) {
                return false;
            }
            $('#upload').ajaxSubmit({
                dataType: 'json',
                url: $('#upload').attr('action'),
                beforeSubmit: function() {
                    $('#upload-button').addClass('disabled').val('Uploading...');
                },
                success: function(data, responseType) {
                    onSuccess(data, responseType, 'upload');
                }
            });
            return false;
        };

        $('form#size input').on('change', function(evt) {
            var $input = $(evt.target);
            var inputName = $input.attr('name');
            var name = inputName.replace(/^size\-/, '')[0];
            var val = parseInt($input.val(), 10) || null;
            var minName = 'min_' + name;
            var sizes = $.parseJSON($('#id_crop-sizes').val());
            var size = sizes[0];
            size[name] = val;
            size[minName] = val || 1;
            $('#id_sizes,#id_crop-sizes').val(JSON.stringify([size]));
            $('#id_thumbs-0-size').val(JSON.stringify(size));
            cropBox.onSuccess(getFormData(), 0);
        });
    });

}(django.jQuery));
