window.CropDuster = {};


(function($) {

    // Backport jQuery.fn.data and jQuery.fn.on/off for jQuery 1.4.2,
    // which ships with Django 1.4
    if ($.prototype.jquery == '1.4.2') {
        var rbrace = /^(?:\{[\w\W]*\}|\[[\w\W]*\])$/,
            rdashAlpha = /-([\da-z])/gi,
            rmultiDash = /([A-Z])/g,
            // Used by jQuery.camelCase as callback to replace()
            fcamelCase = function( all, letter ) {
                 return letter.toUpperCase();
             };
        $.camelCase = function(string) {
            return string.replace(rdashAlpha, fcamelCase);
        };
        $.prototype.data = (function (originalDataMethod) {
            // the parse value function is copied from the jQuery source
             function parseValue(data) {
                 if (typeof data === "string") {
                     try {
                         data = data === "true" ? true :
                             data === "false" ? false :
                             data === "null" ? null :
                             // Only convert to a number if it doesn't change the string
                             +data + "" === data ? +data :
                             rbrace.test(data) ? $.parseJSON(data) : data;
                     } catch (e) {}
                 } else {
                     data = undefined;
                 }
                 return data;
             }

             return function(key, val) {
                 var data;
                 if (typeof key === "undefined") {
                     if (this.length) {
                         data = $.data(this[0]);
                         if (this[0].nodeType === 1) {
                             var attr = this[0].attributes, name;
                             for (var i = 0, l = attr.length; i < l; i++) {
                                 name = attr[i].name;
                                 if (name.indexOf("data-") === 0) {
                                     name = $.camelCase(name.substring(5));
                                     var value = parseValue(attr[i].value);
                                     $(this[0]).data(name, value);
                                     data[name] = value;
                                 }
                             }
                         }
                     }
                     return data;
                 }

                 var result = originalDataMethod.apply(this, arguments);

                 // only when it's an getter and the result from the original data method is null
                 if ((result === null || result === undefined) && val === undefined) {
                     var attrValue = this.attr("data-" + key.replace(rmultiDash, "-$1").toLowerCase());
                     return parseValue(attrValue);
                 }
                 return result;
             };
        })($.prototype.data);

        /**
         * add support for on and off methods
         * @type {Function|*|on}
         */
        $.prototype.on = $.prototype.on || function(/* events [,selector] [,data], handler */) {
            var args = arguments;

            // delegation bind has minimal 3 arguments
            if(args.length >= 3) {
                var events = args[0],
                    selector = args[1],
                    data = (args[3]) ? args[2] : null,
                    handler = (args[3]) ? args[3] : args[2];

                this.bind(events, data, function(ev) {
                    var $target = $(ev.target).closest(selector);
                    if($target.length) {
                        handler.call($target[0], ev);
                    }
                });
            } else {
                this.bind.apply(this, args);
            }

            return this;
        };

        $.prototype.off = $.prototype.off || function(/* events [,selector] [,handler] */) {
            if(arguments.length == 3) {
                throw new Error("Delegated .off is not implemented.");
            } else {
                this.unbind.apply(this, arguments);
            }
            return this;
        };
    }

    var randomDigits = function(length) {
        length = parseInt(length, 10);
        if (!length) {
            return '';
        }
        var zeroes = new Array(length + 1).join('0');
        return (zeroes + Math.ceil(Math.random() * Math.pow(10, length)).toString()).slice(-1 * length);
    };

    var image_css = function(src, width, height, opts, is_ie) {
        var css = '';
        src = encodeURI(src || '') + '?v=' + randomDigits(9);
        css += 'background-image:url("' + src + '");';
        css += 'width:' + width + 'px;';
        css += 'height:' + height + 'px;';
        if (is_ie) {
            var filter = 'progid:DXImageTransform.Microsoft.AlphaImageLoader(src=\'' + src + '\', sizingMethod=\'scale\')';
            css += 'filter:' + filter + ';';
            css += '-ms-filter:"' + filter + '";';
        }
        return css;
    };


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
        show: function(prefix, cropdusterUrl) {
            var params = {
                'image': 'image',
                'id': 'id',
                'thumbs': 'thumbs'
            };
            var data = {};
            for (var paramName in params) {
                var val = $('#id_' + prefix + '-0-' + params[paramName]).val();
                data[paramName] = ($.isArray(val)) ? val.join(',') : val;
            }
            var sizes = $('#id_' + prefix).data('sizes') || [];
            sizes = ($.isArray(sizes)) ? sizes : [];
            data['sizes'] = JSON.stringify(sizes);
            for (var paramName in data) {
                var val = data[paramName];
                if (val) {
                    cropdusterUrl += '&' + paramName + '=' + encodeURI(val || '');
                }
            }
            cropdusterUrl += '&el_id=' + encodeURI(prefix);
            var windowName = String(prefix).replace(/\-/g,"____").split(".").join("___");
            if (typeof GET_params == 'object' && GET_params.cropduster_debug == '1') {
                cropdusterUrl += '&cropduster_debug=1';
            }
            window.open(cropdusterUrl, windowName, 'height=650,width=960,resizable=yes,scrollbars=yes').focus();
        },

        setThumbnails: function(prefix, thumbs) {
            var $select = $('#id_' + prefix + '-0-thumbs');
            $select.find('option').detach();

            for (var name in thumbs) {
                var thumb = thumbs[name];
                if (!thumb.id) {
                    continue;
                }
                var $option = $(document.createElement('OPTION'));
                $option.html(thumb.name).attr({
                    'value': thumb.id,
                    'data-width': thumb.width,
                    'data-height': thumb.height,
                    'data-tmp-file': 'true',
                    'selected': 'selected'
                });
                $select.append($option);
            }
        },

        complete: function(prefix, data) {
            $('#id_' + prefix + '-0-id').val(data.crop.image_id);
            // If no image id, set INITIAL_FORM count to 0
            if ($('#id_' + prefix + '-0-id').val() == '') {
                $('#id_' + prefix + '-INITIAL_FORMS').val('0');
            }
            $('#id_' + prefix + '-0-image').val(data.crop.orig_image);
            $('#id_' + prefix).val(data.crop.orig_image);
            $('#id_' + prefix + '-TOTAL_FORMS').val('1');
            if (typeof data.thumbs != 'object') {
                return;
            }
            CropDuster.setThumbnails(prefix, data.crop.thumbs);
            CropDuster.createThumbnails(prefix);
            $(document).trigger('cropduster:update', [prefix, data]);
        },

        /**
         * Takes an <input class="cropduster-data-field"/> element
         */
        registerInput: function(input) {
            var $input = $(input);
            var data = $input.data();
            data.prefix = $input.attr('id').replace(/^id_/, '');
            var $customField = $input.parent().find('> .cropduster-customfield');

            $customField.click(function(e) {
                var $target = $(e.target).closest('.cropduster-customfield');
                e.preventDefault();
                e.stopPropagation();
                var $targetInput = $target.closest('.form-row,.row,.grp-row').find('.cropduster-data-field').eq(0);
                if (!$targetInput.length) {
                    return;
                }
                var fieldName = $targetInput.attr('name');
                var inputData = $targetInput.data();
                var cropdusterUrl = $target.data('cropdusterUrl');
                var arg = (cropdusterUrl.indexOf('?') >= 0) ? '&' : '?';
                if (inputData.uploadTo) {
                    cropdusterUrl += arg + 'upload_to=' + encodeURI(inputData.uploadTo);
                }
                CropDuster.show(fieldName, cropdusterUrl);
            });

            var $inlineForm = $input.closest('.cropduster-form');

            CropDuster.mediaUrl = $inlineForm.data('mediaUrl');

            var name = $input.attr('name');
            var matches = name.match(/(?:\d+|__prefix__|empty)\-([^\-]+)$/);
            if (matches) {
                name = matches[1];
            }

            var $inputRow = $input.closest('.grp-row.' + name + ',.row.' + name + ',.form-row.field-' + name);
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
                var $row = $(this).closest('.cropduster-form');
                if (this.checked) {
                    $row.addClass('predelete grp-predelete');
                } else {
                    $row.removeClass('predelete grp-predelete');
                }
            });
            // Re-initialize thumbnail images. This is necessary in the event that
            // that the cropduster admin form doesn't have an image id but has thumbnails
            // (for example when a new image is uploaded and the post is saved, but there is
            // a validation error on the page)
            CropDuster.createThumbnails(data.prefix);

        },

        createThumbnails: function(prefix) {
            var $input = $("#id_" + prefix);
            var data = $input.data();
            if (!$input.length) {
                return;
            }
            var image = $('#id_' + prefix + '-0-image').val();
            if (!image) {
                return;
            }
            // The groups in this regex correspond to the path, basename (sans
            // extension), and file extension of a file path or url.
            var matches = image.match(/^(.*)(\/(?:[^\/](?!\.[^\.\/\?]+))*[^\.\/\?])(\.[^\.\/\?]+)?$/);
            if (!matches) {
                return;
            }
            var path = matches[1];
            var ext = matches[3];

            var thumbData = {};

            var sizes = {};
            $.each(data.sizes, function(i, size) {
                if (!size || !size.name) return;
                sizes[size.name] = size;
            });

            $('#id_' + prefix + '-0-thumbs option:selected').each(function(i, el) {
                var $el = $(el);
                var name = $el.html();
                var slug = name;
                var data = $el.data() || {};
                if (!data.width || !data.height) {
                    return;
                }
                if (data.tmpFile) {
                    name += "_tmp";
                }
                var url = [CropDuster.mediaUrl, path, name + ext].join('/');
                // This is in place of a negative lookbehind. It replaces all
                // double slashes that don't follow a colon.
                url = url.replace(/(:)?\/+/g, function($0, $1) { return $1 ? $0 : '/'; });
                thumbData[slug] = {
                    'image_url': url,
                    'size_slug': slug,
                    'width': data.width,
                    'height': data.height
                };
            });
            var $thumb = $input.closest('.cropduster-form').find('.cropduster-images');
            $thumb.find('a').remove();

            $.each(data.sizes, function(i, size) {
                if (!size || !size.name) return;
                if (thumbData[size.name]) {
                    $thumb.html($thumb.html() + $.render.cropdusterImage(thumbData[size.name]));
                }
            });
        },

        removeSize: function(prefix, sizeName) {
            var $selector = $('#id_' + prefix);

            var sizes = $selector.data('sizes');

            for (var i = 0; i < sizes.length; i++) {
                if (sizes[i].name == sizeName) {
                    break;
                }
            }

            // Check that we found the size we need
            if (i == sizes.length) {
                return;
            }

            // values returned from $.fn.data() are references, so any modifications
            // we make to the array will persist across calls to $.fn.data()
            var removedSizes = sizes.splice(i, 1);

            var removedSizesData = $selector.data('removedSizes') || {};
            if ($.isEmptyObject(removedSizesData)) {
                $selector.data('removedSizes', removedSizesData);
            }

            removedSizesData[sizeName] = {
                index: i,
                size: removedSizes[0]
            };
        },

        restoreSize: function(prefix, sizeName) {
            var $selector = $('#id_' + prefix);
            var sizes = $selector.data('sizes');
            var removedSizesData = $selector.data('removedSizes');

            // If no size with sizeName has yet been removed, return
            if (!removedSizesData || !removedSizesData[sizeName]) {
                return;
            }

            var sizeToRestore = removedSizesData[sizeName];
            sizes.splice(sizeToRestore.index, 0, sizeToRestore.size);
            delete removedSizesData[sizeName];
        }

    };

    $(document).ready(function() {
        if (typeof GET_params == 'object' && GET_params.cropduster_debug == '1') {
            $('body').addClass('cropduster-debug');
        }
        $('.cropduster-data-field').each(function(i, idField) {
            CropDuster.registerInput(idField);
        });
    });

})((typeof window.django != 'undefined') ? django.jQuery : jQuery);
