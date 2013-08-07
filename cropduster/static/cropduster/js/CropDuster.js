window.CropDuster = {};


(function($) {

    CropDuster = {

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

        getVal: function(prefix, name) {
            var val = $('#id_' + prefix + '-0-' + name).val();
            return (val) ? encodeURI(val) : val;
        },

        setVal: function(prefix, name, val) {
            $('#id_' + prefix + '-0-' + name).val(val);
        },

        // open upload window
        show: function(id, href, imageId) {
            var id2=String(id).replace(/\-/g,"____").split(".").join("___");
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
                href += '&ext='  + CropDuster.getVal(id, '_extension');
            }
            href += '&el_id=' + encodeURI(id);
            var win = window.open(href, id2, 'height=650,width=960,resizable=yes,scrollbars=yes');
            win.focus();
        },

        setThumbnails: function(prefix, thumbs) {
            var select = $('#id_' + prefix + '-0-thumbs');
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

        complete: function(prefix, data) {
            $('#id_' + prefix).val(data.relpath);
            CropDuster.setVal(prefix, 'id', data.id);
            CropDuster.setVal(prefix, 'crop_x', data.x);
            CropDuster.setVal(prefix, 'crop_y', data.y);
            CropDuster.setVal(prefix, 'crop_w', data.w);
            CropDuster.setVal(prefix, 'crop_h', data.h);
            CropDuster.setVal(prefix, 'path', data.path);
            CropDuster.setVal(prefix, 'default_thumb', data.default_thumb);
            CropDuster.setVal(prefix, '_extension', data.extension);
            $('#id_' + prefix + '-TOTAL_FORMS').val('1');
            var thumbs;

            if (data.thumbs) {
                thumbs = $.parseJSON(data.thumbs);
                CropDuster.setThumbnails(prefix, thumbs);
            }
            var defaultThumbName = CropDuster.defaultThumbs[prefix];
            if (data.thumb_urls) {
                var thumbUrls = $.parseJSON(data.thumb_urls);
                var html = '';
                var i = 0;
                for (var name in thumbUrls) {
                    if (name != defaultThumbName) {
                        continue;
                    }
                    var url = thumbUrls[name];
                    var className = "preview";
                    if (i == 0) {
                        className += " first";
                    }
                    // Append random get variable so that it refreshes
                    url += '?rand=' + CropDuster.generateRandomId();
                    html += '<img id="id_' + prefix + '_image_' + name + '" src="' + url + '" class="' + className + '" />';
                    i++;
                }
                $('#preview_id_' + prefix).html(html);
            }
        },

        /**
         * Takes an <input class="cropduster-data-field"/> element
         */
        registerInput: function(input) {
            var $input = $(input);
            var data = $input.data();
            var name = $input.attr('name');

            CropDuster.sizes[name] = JSON.stringify(data.sizes);
            CropDuster.autoSizes[name] = JSON.stringify(data.autoSizes) || null;
            CropDuster.minSize[name] = data.minSize;
            CropDuster.defaultThumbs[name] = data.defaultThumb;
            CropDuster.aspectRatios[name] = data.aspectRatio;

            var $customField = $input.parent().find('> .cropduster-customfield');

            var uploadUrl = $customField.attr('data-upload-url');

            var prefix = $input.attr('name');

            $customField.click(function(e) {
                var $target = $(e.target);
                e.preventDefault();
                var $targetParent = $target.closest('.row,.grp-row');
                var $targetInput = $targetParent.find('input');
                if (!$targetInput.length) {
                    return;
                }
                $targetInput = $($targetInput[0]);
                var name = $targetInput.attr('name');
                var imageId = $targetInput.val();

                if (name.indexOf(prefix) == -1) {
                    var $realInput = $('#id_' + prefix + '-0-id');
                    if ($realInput && $realInput.length) {
                        imageId = $realInput.val();
                        $targetParent = $realInput.closest('.row,.grp-row');
                    }
                }

                var fieldName = $targetParent.find('.cropduster-data-field').attr('name');
                CropDuster.uploadUrl = $target.attr('data-upload-url');
                CropDuster.show(fieldName, uploadUrl, imageId);
            });


            var $inlineForm = $input.parent().find('.cropduster-form').first();

            CropDuster.staticUrl = $inlineForm.attr('data-static-url');

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
            $inlineForm.find('.id').each(function(i, el) {
                if ($(el).parents('.inline-related').hasClass('empty-form')) {
                    return;
                }
                var path = $customField.data('imagePath');
                //  var path = $('#id_' + prefix + '-0-path').val();
                ext = $('#id_' + prefix + '-0-_extension').val();
                var html = '';
                var defaultThumbName = CropDuster.defaultThumbs[prefix];

                $('#id_' + prefix + '-0-thumbs option:selected').each(function(i, el) {
                    var name = $(el).html();
                    if (name != defaultThumbName) {
                        return;
                    }
                    var url = CropDuster.staticUrl + '/' + path + '/' + name + '.' + ext;
                    // This is in place of a negative lookbehind. It replaces all
                    // double slashes that don't follow a colon.
                    url = url.replace(/(:)?\/+/g, function($0, $1) { return $1 ? $0 : '/'; });
                    url += '?rand=' + CropDuster.generateRandomId();
                    var className = 'preview';
                    if (i === 0) {
                        className += ' first';
                    }
                    html += '<img id="id_' + prefix + '0--id_image_' + name + '" src="' + url + '" class="' + className + '" />';
                });
                $customField.find('.cropduster-preview').html(html);
            });

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
