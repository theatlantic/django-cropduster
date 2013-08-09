window.CropDuster = {};


(function($) {

    var image_css = function(src, width, height, opts, is_ie) {
        var css = '';
        css += 'background-image:url(' + src + ');';
        css += 'width:' + width + 'px;';
        css += 'height:' + height + 'px;';
        if (is_ie) {
            var filter = 'progid:DXImageTransform.Microsoft.AlphaImageLoader(src=\'' + src + '\', sizingMethod=\'scale\')';
            css += 'filter:' + filter + ';';
            css += '-ms-filter:"' + filter + '";';
        }
        return css;
    };

    // jsrender templates
    if ($.views) {
        $.views.helpers({
            image_css: image_css,
            ie_image_css: function(src, width, height, opts) {
                return image_css.call(this, src, width, height, opts, true);
            }
        });

        $.templates({
            cropdusterImage: '<a target="_blank" class="cropduster-image cropduster-image-{{>size_slug}}" href="{{>image_url}}">' +
                '<!' + '--[if lt IE 9]' + '>' +
                '<span style="{{>~ie_image_css(image_url, width, height)}}"></span>' +
                '<![endif]--><![if gte IE 9]>' +
                '   <span style="{{>~image_css(image_url, width, height)}}"></span>' +
                '<![endif]></a>'
        });
    }

    CropDuster = {

        mediaUrl: '',

        // open upload window
        show: function(prefix, uploadUrl) {
            var href = uploadUrl;
            var params = {
                'x': 'crop_x',
                'y': 'crop_y',
                'w': 'crop_w',
                'h': 'crop_h',
                'path': 'path',
                'ext': '_extension',
                'id': 'id'
            };
            var hasData = false;
            for (var paramName in params) {
                var val = encodeURI($('#id_' + prefix + '-0-' + params[paramName]).val() || '');
                href += '&' + paramName + '=' + val;
                hasData = hasData || !!val;
            }
            if (hasData) {
                uploadUrl = href;
            }
            uploadUrl += '&el_id=' + encodeURI(prefix);
            var windowName = String(prefix).replace(/\-/g,"____").split(".").join("___");
            window.open(uploadUrl, windowName, 'height=650,width=960,resizable=yes,scrollbars=yes').focus();
        },

        setThumbnails: function(prefix, thumbs) {
            var $select = $('#id_' + prefix + '-0-thumbs');
            $select.find('option').detach();
            for (var sizeName in thumbs) {
                var thumbId = thumbs[sizeName];
                var option = $(document.createElement('OPTION'));
                option.attr('value', thumbId);
                option.html(sizeName);
                $select.append(option);
                option.selected = true;
                option.attr('selected', 'selected');
            }
        },

        complete: function(prefix, data) {
            var $input = $('#id_' + prefix);
            var formData = {
                'id': data.id,
                'crop_x': data.x,
                'crop_y': data.y,
                'crop_w': data.w,
                'crop_h': data.h,
                'path': data.path,
                '_extension': data.extension
            };
            $input.val(data.relpath);

            for (var fieldName in formData) {
                var value = formData[fieldName];
                $('#id_' + prefix + '-0-' + fieldName).val(value);
            }
            $('#id_' + prefix + '-TOTAL_FORMS').val('1');
            var thumbs;

            if (data.thumbs) {
                thumbs = $.parseJSON(data.thumbs);
                CropDuster.setThumbnails(prefix, thumbs);
            }
            CropDuster.createThumbnails(prefix, true);
        },

        renderThumbnails: function($input, thumbData) {
        },

        /**
         * Takes an <input class="cropduster-data-field"/> element
         */
        registerInput: function(input) {
            var $input = $(input);
            var data = $input.data();
            var $customField = $input.parent().find('> .cropduster-customfield');

            $customField.click(function(e) {
                var $target = $(e.target).closest('.cropduster-customfield');
                e.preventDefault();
                e.stopPropagation();
                var $targetInput = $target.closest('.row,.grp-row').find('.cropduster-data-field').eq(0);
                if (!$targetInput.length) {
                    return;
                }
                var fieldName = $targetInput.attr('name');
                var inputData = $targetInput.data();
                var uploadUrl = $target.data('uploadUrl');
                var arg = (uploadUrl.indexOf('?') >= 0) ? '&' : '?';
                if (inputData.uploadTo) {
                    uploadUrl += arg + 'upload_to=' + encodeURI(inputData.uploadTo);
                }
                CropDuster.show(fieldName, uploadUrl);
            });

            var $inlineForm = $input.parent().find('.cropduster-form').first();

            CropDuster.mediaUrl = $inlineForm.data('mediaUrl');

            var name = $input.attr('name');
            var matches = name.match(/(?:\d+|__prefix__|empty)\-([^\-]+)$/);
            if (matches) {
                name = matches[1];
            }

            var $inputRow = $input.parents('.grp-row.' + name + ',.row.' + name);
            if ($inputRow.length) {
                var inputLabel = $inputRow.find('label').html();
                if (inputLabel) {
                    inputLabel = inputLabel.replace(/:$/, '');
                    $inlineForm.find('h2.collapse-handler').each(function(header) {
                        header.innerHTML = inputLabel;
                    });
                }
                $inputRow.find('.cropduster-text-field').hide();
            }

            $inlineForm.find('span.delete input').change(function() {
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
            CropDuster.createThumbnails(data.prefix);

        },

        createThumbnails: function(prefix, preview) {
            $input = $("input[data-prefix='" + prefix + "']");
            var data = $input.data();
            if (!$input.length) {
                return;
            }
            var path = $('#id_' + prefix + '-0-path').val();
            var ext = $('#id_' + prefix + '-0-_extension').val();

            var thumbData = {};

            $('#id_' + prefix + '-0-thumbs option:selected').each(function(i, el) {
                var name = $(el).html();
                var slug = name;
                if (!data.sizes[name]) {
                    return;
                }
                if (preview) {
                    name += "_tmp";
                }
                var url = CropDuster.mediaUrl + '/' + path + '/' + name + '.' + ext;
                // This is in place of a negative lookbehind. It replaces all
                // double slashes that don't follow a colon.
                url = url.replace(/(:)?\/+/g, function($0, $1) { return $1 ? $0 : '/'; });
                thumbData[name] = {
                    'image_url': url,
                    'size_slug': slug,
                    'width': data.sizes[slug][0],
                    'height': data.sizes[slug][1]
                };
            });
            var $thumb = $input.closest('.row,.grp-row').find('.cropduster-images');
            $thumb.find('a').remove();
            for (var name in thumbData) {
                $thumb.html($thumb.html() + $.render.cropdusterImage(thumbData[name]));
            }
        },

        generateRandomId: function() {
            return ('000000000' + Math.ceil(Math.random()*1000000000).toString()).slice(-9);
        }
    };

    $(document).ready(function() {
        $('.cropduster-data-field').each(function(i, idField) {
            CropDuster.registerInput(idField);
        });
    });

})((typeof window.django != 'undefined') ? django.jQuery : jQuery);
