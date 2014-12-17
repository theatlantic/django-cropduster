/**
 * @license Copyright (c) 2003-2013, CKSource - Frederico Knabben. All rights reserved.
 * For licensing, see LICENSE.html or http://ckeditor.com/license
 */

CKEDITOR.dialog.add('cropduster', function (editor) {

    'use strict';

    if (typeof editor.config.cropduster_dialogAdd == 'function') {
        editor.config.cropduster_dialogAdd(editor);
    }

    // RegExp: 123, 123px, empty string ""
    var regexGetSizeOrEmpty = /(^\s*(\d+)(px)?\s*$)|^$/i,

        lockButtonId = CKEDITOR.tools.getNextId(),
        resetButtonId = CKEDITOR.tools.getNextId(),

        lang = editor.lang.cropduster,
        commonLang = editor.lang.common,

        lockResetStyle = 'margin-top:18px;width:40px;height:20px;',
        lockResetHtml = new CKEDITOR.template(
            '<div>' +
            '<a href="javascript:void(0)" tabindex="-1" title="' + lang.lockRatio + '" class="cke_btn_locked" id="{lockButtonId}" role="checkbox">' +
            '<span class="cke_icon"></span>' +
            '<span class="cke_label">' + lang.lockRatio + '</span>' +
            '</a>' +

            '<a href="javascript:void(0)" tabindex="-1" title="' + lang.resetSize + '" class="cke_btn_reset" id="{resetButtonId}" role="button">' +
            '<span class="cke_label">' + lang.resetSize + '</span>' +
            '</a>' +
            '</div>').output({
            lockButtonId: lockButtonId,
            resetButtonId: resetButtonId
        }),

        // Global variables referring to the dialog's context.
        doc, widget, image,

        // Global variable referring to this dialog's image pre-loader.
        preLoader,

        // Global variables holding the original size of the image.
        domWidth, domHeight,

        // Global variables related to image pre-loading.
        preLoadedWidth, preLoadedHeight, srcChanged,

        // Global variables related to size locking.
        lockRatio, userDefinedLock,

        // Global variables referring to dialog fields and elements.
        lockButton, resetButton, widthField, heightField, srcField,
        // cropduster iframe
        cropdusterIframe;

    // Validates dimension. Allowed values are:
    // "123px", "123", "" (empty string)

    function validateDimension() {
        var match = this.getValue().match(regexGetSizeOrEmpty),
            isValid = !! (match && parseInt(match[1], 10) !== 0);

        if (!isValid)
            alert(commonLang['invalid' + CKEDITOR.tools.capitalize(this.id)]);

        return isValid;
    }

    // Creates a function that pre-loads images. The callback function passes
    // [image, width, height] or null if loading failed.
    //
    // @returns {Function}

    function createPreLoader() {
        var image = doc.createElement('img'),
            listeners = [];

        function addListener(event, callback) {
            listeners.push(image.once(event, function (evt) {
                removeListeners();
                callback(evt);
            }));
        }

        function removeListeners() {
            var l;

            while ((l = listeners.pop()))
                l.removeListener();
        }

        // @param {String} src.
        // @param {Function} callback.
        return function (src, callback, scope) {
            addListener('load', function () {
                callback.call(scope, image, image.$.width, image.$.height);
            });

            addListener('error', function () {
                callback(null);
            });

            addListener('abort', function () {
                callback(null);
            });

            image.setAttribute('src', src + '?' + Math.random().toString(16).substring(2));
        };
    }

    function onChangeDimension() {
        // If ratio is un-locked, then we don't care what's next.
        if (!lockRatio)
            return;

        var value = this.getValue();

        // No reason to auto-scale or unlock if the field is empty.
        if (!value)
            return;

        // If the value of the field is invalid (e.g. with %), unlock ratio.
        if (!value.match(regexGetSizeOrEmpty))
            toggleLockDimensions(false);

        // No automatic re-scale when dimension is '0'.
        if (value === '0')
            return;

        var isWidth = this.id == 'width',
            // If dialog opened for the new image, domWidth and domHeight
            // will be empty. Use dimensions from pre-loader in such case instead.
            width = domWidth || preLoadedWidth,
            height = domHeight || preLoadedHeight;

        // If changing width, then auto-scale height.
        if (isWidth)
            value = Math.round(height * (value / width));

        // If changing height, then auto-scale width.
        else
            value = Math.round(width * (value / height));

        // If the value is a number, apply it to the other field.
        if (!isNaN(value))
            (isWidth ? heightField : widthField).setValue(value);
    }

    // Set-up function for lock and reset buttons:
    //     * Adds lock and reset buttons to focusables. Check if button exist first
    //       because it may be disabled e.g. due to ACF restrictions.
    //     * Register mouseover and mouseout event listeners for UI manipulations.
    //     * Register click event listeners for buttons.

    function onLoadLockReset() {
        var dialog = this.getDialog();

        function setupMouseClasses(el) {
            el.on('mouseover', function () {
                this.addClass('cke_btn_over');
            }, el);

            el.on('mouseout', function () {
                this.removeClass('cke_btn_over');
            }, el);
        }

        // Create references to lock and reset buttons for this dialog instance.
        lockButton = doc.getById(lockButtonId);
        resetButton = doc.getById(resetButtonId);

        // Activate (Un)LockRatio button
        if (lockButton) {
            dialog.addFocusable(lockButton, 4);

            lockButton.on('click', function (evt) {
                toggleLockDimensions();
                evt.data && evt.data.preventDefault();
            }, this.getDialog());

            setupMouseClasses(lockButton);
        }

        // Activate the reset size button.
        if (resetButton) {
            dialog.addFocusable(resetButton, 5);

            // Fills width and height fields with the original dimensions of the
            // image (stored in widget#data since widget#init).
            resetButton.on('click', function (evt) {
                // If there's a new image loaded, reset button should revert
                // cached dimensions of pre-loaded DOM element.
                if (srcChanged) {
                    widthField.setValue(preLoadedWidth);
                    heightField.setValue(preLoadedHeight);
                }

                // If the old image remains, reset button should revert
                // dimensions as loaded when the dialog was first shown.
                else {
                    widthField.setValue(domWidth);
                    heightField.setValue(domHeight);
                }

                evt.data && evt.data.preventDefault();
            }, this);

            setupMouseClasses(resetButton);
        }
    }

    function toggleLockDimensions(enable) {
        // No locking if there's no radio (i.e. due to ACF).
        if (!lockButton) {
            return;
        }
        var width, height;

        // Check image ratio and original image ratio, but respecting user's
        // preference. This is performed when a new image is pre-loaded
        // but not if user already manually locked the ratio.
        if (enable == 'check' && !userDefinedLock) {
            width = widthField.getValue();
            height = heightField.getValue();

            var domRatio = preLoadedWidth * 1000 / preLoadedHeight,
                ratio = width * 1000 / height;

            lockRatio = false;

            // Lock ratio, if there is no width and no height specified.
            if (!width && !height) {
                lockRatio = true;
            // Lock ratio if there is at least width or height specified,
            // and the old ratio that matches the new one.
            } else if (!isNaN(domRatio + ratio) && Math.round(domRatio) == Math.round(ratio)) {
                lockRatio = true;
            }
        // True or false.
        } else if (typeof enable == 'boolean') {
            lockRatio = enable;
        // Undefined. User changed lock value.
        } else {
            userDefinedLock = true;
            lockRatio = !lockRatio;

            width = widthField.getValue();
            // Automatically adjust height to width to match
            // the original ratio (based on dom- dimensions).
            if (lockRatio && width) {
                height = domHeight / domWidth * width;

                if (!isNaN(height))
                    heightField.setValue(Math.round(height));
            }
        }

        lockButton[lockRatio ? 'removeClass' : 'addClass']('cke_btn_unlocked');
        lockButton.setAttribute('aria-checked', lockRatio);

        // Ratio button hc presentation - WHITE SQUARE / BLACK SQUARE
        if (CKEDITOR.env.hc) {
            var icon = lockButton.getChild(0);
            icon.setHtml(lockRatio ? CKEDITOR.env.ie ? '\u25A0' : '\u25A3' : CKEDITOR.env.ie ? '\u25A1' : '\u25A2');
        }
    }

    var toggleDimensions = function(enable) {
        var method = (enable) ? 'enable' : 'disable';
        widthField[method]();
        heightField[method]();
    };

    var updateValue = function(value) {
        toggleDimensions(false);
        // Remember that src is different than default.
        if (value !== widget.data.src) {
            // Update dimensions of the image once it's preloaded.
            preLoader(value, function (image, width, height) {
                // Re-enable width and height fields.
                toggleDimensions(true);
                // There was problem loading the image. Unlock ratio.
                if (!image) {
                    return toggleLockDimensions(false);
                }
                // Fill width field with the width of the new image.
                widthField.setValue(width);
                // Fill height field with the height of the new image.
                heightField.setValue(height);
                // Cache the new width.
                preLoadedWidth = width;
                // Cache the new height.
                preLoadedHeight = height;
                // Check for new lock value if image exist.
                toggleLockDimensions('check');
            });
            srcChanged = true;
        // Value is the same as in widget data but is was
        // modified back in time. Roll back dimensions when restoring
        // default src.
        } else if (srcChanged) {
            // Re-enable width and height fields.
            toggleDimensions(true);
            // Restore width field with cached width.
            widthField.setValue(domWidth);
            // Restore height field with cached height.
            heightField.setValue(domHeight);
            // Src equals default one back again.
            srcChanged = false;
        // Value is the same as in widget data and it hadn't
        // been modified.
        } else {
            // Re-enable width and height fields.
            toggleDimensions(true);
        }
    };

    var isPlainObject = function(obj) {
        // Must be an Object.
        // Because of IE, we also have to check the presence of the constructor property.
        // Make sure that DOM nodes and window objects don't pass through, as well
        if (!obj || typeof obj !== "object" || obj.nodeType || obj.window == obj) {
            return false;
        }

        // Not own constructor property must be Object
        if (obj.constructor &&
            !Object.prototype.hasOwnProperty.call(obj, "constructor") &&
            !Object.prototype.hasOwnProperty.call(obj.constructor.prototype, "isPrototypeOf")) {
            return false;
        }

        // Own properties are enumerated firstly, so to speed up,
        // if last one is own, then all properties are own.

        var key;
        for (key in obj) {}

        return key === undefined || Object.prototype.hasOwnProperty.call(obj, key);
    };

    var okButton = CKEDITOR.dialog.okButton.override({
        onClick: function(evt) {
            var $j = cropdusterIframe.iframeElement.$.contentWindow.$;
            if ($j) {
                var $cropButton = $j('#crop-button');
                if ($j.length && !$cropButton.hasClass('disabled')) {
                    $cropButton.click();
                    return;
                }
            }
            var dialog = evt.data.dialog;
            if (dialog.fire('ok', {hide: true}).hide !== false) {
                dialog.hide();
            }
        }
    });

    var tabElements = [{
        id: 'iframe',
        type: 'html',
        html: '<div style="width:100%;text-align:center;">' + '<iframe style="border:0;width:650px;height:400px;font-size:20px" scrolling="no" frameborder="0" allowTransparency="true"></iframe>' + '</div>',
        onLoad: function (widget) {},
        setup: function (widget) {

            var dialogElement = this.getDialog().getElement();
            dialogElement.addClass('cke_editor_cropduster_content_dialog');
            var tabs = dialogElement.findOne('.cke_dialog_tabs');
            if (tabs) {
                tabs.hide();
            }
            var contents = dialogElement.findOne('.cke_dialog_contents');
            if (contents) {
                contents.setStyles({'border-top': '0', 'margin-top': '0'});
            }

            cropdusterIframe = {
                setup: function (domId, baseUrl) {
                    this.iframeElement = CKEDITOR.document.getById(domId).getChild(0)
                    this.baseUrl = baseUrl;
                    this.callback_fn = domId.replace(/_uiElement$/, '') + '_callback';

                    var image = widget.parts.image;
                    var params = {'callback_fn': this.callback_fn};
                    if (widget.config.uploadTo) {
                        params['upload_to'] = widget.config.uploadTo;
                    }
                    if (widget.config.previewSize) {
                        if (Object.prototype.toString.call(widget.config.previewSize) == '[object Array]') {
                            if (widget.config.previewSize.length == 2) {
                                params['preview_size'] = widget.config.previewSize.join('x');
                            }
                        }
                    }
                    if (image.$.naturalWidth != image.$.width) {
                        params['max_w'] = image.$.width;
                    }
                    if (widget.data && widget.data.src) {
                        params['image'] = widget.data.src;
                    }
                    if (widget.config.urlParams && isPlainObject(widget.config.urlParams)) {
                        params = CKEDITOR.tools.extend({}, params, widget.config.urlParams);
                    }
                    this.params = params;
                    this.reload();
                },
                getUrl: function () {
                    var urlQuery = [];
                    for (var k in this.params) {
                        urlQuery.push([k, encodeURIComponent(this.params[k])].join('='));
                    }
                    return this.baseUrl + urlQuery.join('&');
                },
                reload: function () {
                    var url = this.getUrl();
                    this.iframeElement.$.src = url;
                }
            }
            cropdusterIframe.setup(this.domId, widget.config.url + '?');
            widget.cropdusterIframe = cropdusterIframe;

            var self = this;
            var callback = function (prefix, data) {
                if (typeof data == 'object' && Object.prototype.toString.call(data.thumbs) == '[object Array]' && data.thumbs.length) {
                    var thumbData = data.thumbs[0];
                    widthField.setValue(thumbData.width);
                    widget.setData('width', thumbData.width);
                    heightField.setValue(thumbData.height);
                    widget.setData('height', thumbData.height);
                    srcField.setValue(thumbData.url);
                    updateValue(cropdusterIframe.getUrl());
                }
                var dialog = self.getDialog();
                if (dialog.fire('ok', {hide: true}).hide !== false) {
                    dialog.hide();
                }
            };
            window[cropdusterIframe.callback_fn] = callback;
        }
    }, {
        id: 'hasCaption',
        type: 'checkbox',
        label: lang.captioned,
        setup: function (widget) {
            this.setValue(widget.data.hasCaption);
        },
        commit: function (widget) {
            widget.setData('hasCaption', this.getValue());
        }
    }];

    var tabElementIdIndexMap = {};

    var i;

    for (i = 0; i < tabElements.length; i++) {
        tabElementIdIndexMap[tabElements[i].id] = i;
    }

    var configTabElements = editor.config.cropduster_tabElements;

    if (typeof configTabElements == 'object' && Object.prototype.toString.call(configTabElements) == '[object Array]') {
        for (i = 0; i < configTabElements.length; i++) {
            var tabElement = configTabElements[i];
            var existingTabIndex = tabElementIdIndexMap[tabElement.id];
            if (typeof existingTabIndex != 'undefined') {
                tabElements[existingTabIndex] = tabElement;
            } else {
                tabElements.push(tabElement);
            }
        }
    }

    return {
        title: lang.title,
        minWidth: 650,
        minHeight: 500,
        buttons: [ CKEDITOR.dialog.cancelButton, okButton ],
        onLoad: function () {
            // Create a "global" reference to the document for this dialog instance.
            doc = this._.element.getDocument();
            // Create a pre-loader used for determining dimensions of new images.
            preLoader = createPreLoader();
        },
        onShow: function () {
            // Create a "global" reference to edited widget.
            widget = this.widget;
            // Create a "global" reference to widget's image.
            image = widget.parts.image;
            // Reset global variables.
            preLoadedWidth = preLoadedHeight = srcChanged =
                userDefinedLock = lockRatio = false;
            // TODO: IE8
            // Get the natural width of the image.
            domWidth = image.$.naturalWidth;
            // TODO: IE8
            // Get the natural height of the image.
            domHeight = image.$.naturalHeight;
            // Determine image ratio lock on startup. Delayed, waiting for
            // fields to be filled with setup functions.
            setTimeout(function() {
                toggleLockDimensions('check');
            });
        },
        onOk: function(evt) {
            var retval = CKEDITOR.dialog.validate.notEmpty(lang.urlMissing).call(this._.contents.info.src),
                invalid = typeof(retval) == 'string' || retval === false;
            if (invalid) {
                evt.data.hide = false;
                evt.stop();
                if (this.fire('cancel', {hide: true}).hide !== false) {
                    this.hide();
                }
                return false;
            }
            return true;
        },
        contents: [{
            id: 'tab-basic',
            label: 'Basic',
            elements: tabElements
        }, {
            id: 'info',
            label: 'Advanced',
            elements: [{
                id: 'src',
                type: 'text',
                label: commonLang.url,
                onLoad: function() {
                    srcField = this;
                },
                onKeyup: function () {
                    var value = this.getValue();
                    updateValue(value);
                },
                setup: function (widget) {
                    this.setValue(widget.data.src);
                },
                commit: function (widget) {
                    widget.setData('src', this.getValue());
                },
                validate: function() {
                    return true;
                }
            }, {
                id: 'alt',
                type: 'text',
                label: lang.alt,
                setup: function (widget) {
                    this.setValue(widget.data.alt);
                },
                commit: function (widget) {
                    widget.setData('alt', this.getValue());
                }
            }, {
                type: 'hbox',
                widths: ['25%', '25%', '50%'],
                requiredContent: 'img[width,height]',
                children: [{
                    type: 'text',
                    width: '45px',
                    id: 'width',
                    label: commonLang.width,
                    validate: validateDimension,
                    onKeyUp: onChangeDimension,
                    onLoad: function () {
                        widthField = this;
                    },
                    setup: function (widget) {
                        this.setValue(widget.data.width);
                    },
                    commit: function (widget) {
                        widget.setData('width', this.getValue());
                    }
                }, {
                    type: 'text',
                    id: 'height',
                    width: '45px',
                    label: commonLang.height,
                    validate: validateDimension,
                    onKeyUp: onChangeDimension,
                    onLoad: function () {
                        heightField = this;
                    },
                    setup: function (widget) {
                        this.setValue(widget.data.height);
                    },
                    commit: function (widget) {
                        widget.setData('height', this.getValue());
                    }
                }, {
                    id: 'lock',
                    type: 'html',
                    style: lockResetStyle,
                    onLoad: onLoadLockReset,
                    html: lockResetHtml
                }]
            }]
        }]
    };
});