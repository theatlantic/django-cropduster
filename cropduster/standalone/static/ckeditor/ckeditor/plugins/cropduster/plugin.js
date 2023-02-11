/**
 * @license Copyright (c) 2003-2013, CKSource - Frederico Knabben. All rights reserved.
 * For licensing, see LICENSE.html or http://ckeditor.com/license
 */

(function() {

    'use strict';

    var template = '<img alt="" src="" />',
        templateBlock = '<figure>' +
                template +
                '<figcaption class="caption">Caption</figcaption>' +
            '</figure>',
        regexPercent = /^\s*(\d+\%)\s*$/i;

    var CKEDITOR = window.CKEDITOR;

    CKEDITOR.plugins.add('cropduster', {
        lang: 'en', // %REMOVE_LINE_CORE%
        requires: 'widget,dialog',
        icons: 'cropduster',
        hidpi: false,

        onLoad: function(editor) {
            CKEDITOR.addCss(
            '.cke_editable.cke_cropduster_sw, .cke_editable.cke_cropduster_sw *{cursor:sw-resize !important}' +
            '.cke_editable.cke_cropduster_se, .cke_editable.cke_cropduster_se *{cursor:se-resize !important}' +
            '.cke_cropduster_resizer{' +
                'display:none;' +
                'position:absolute;' +
                'width:10px;' +
                'height:10px;' +
                'bottom:-5px;' +
                'right:-5px;' +
                'background:#000;' +
                'outline:1px solid #fff;' +
                'cursor:se-resize;' +
            '}' +
            '.cke_cropduster_resizer_wrapper{' +
                'position:relative;' +
                'display:inline-block;' +
                'line-height:0;' +
            '}' +
            // Bottom-left corner style of the resizer.
            '.cke_cropduster_resizer.cke_cropduster_resizer_left{' +
                'right:auto;' +
                'left:-5px;' +
                'cursor:sw-resize;' +
            '}' +
            '.cke_widget_wrapper:hover .cke_cropduster_resizer,' +
            '.cke_cropduster_resizer.cke_cropduster_resizing{' +
                'display:block' +
            '}');
        },

        init: function(editor) {
            if (typeof editor.config.cropduster_beforeInit == 'function') {
                editor.config.cropduster_beforeInit(editor);
            }

            var widgetConfig = CKEDITOR.tools.clone(cropduster);
            if (typeof editor.config.cropduster_widgetConfig == 'function') {
                var customWidgetConfig = editor.config.cropduster_widgetConfig(cropduster);
                for (var k in customWidgetConfig) {
                    widgetConfig[k] = customWidgetConfig[k];
                }
            }
            // Register the widget.
            editor.widgets.add('cropduster', widgetConfig);

            // Add toolbar button for this plugin.
            editor.ui.addButton && editor.ui.addButton('cropduster', {
                label: 'CropDuster Image',
                command: 'cropduster',
                toolbar: 'insert,10'
            });

            if (typeof editor.ui.items.Image == 'object') {
                editor.ui.items.Image.label = "Legacy Image Upload";
                editor.ui.items.Image.args[0].label = "Legacy Image Upload";
            }

            // Register context menu option for editing widget.
            if (editor.contextMenu) {
                editor.addMenuGroup('cropduster', 10);

                editor.addMenuItem('cropduster', {
                    label: editor.lang.cropduster.menu,
                    command: 'cropduster',
                    group: 'cropduster'
                });
            }

            CKEDITOR.dialog.add('cropduster', this.path + 'dialogs/cropduster.js');
        },

        afterInit: function(editor) {
            var align = { left:1,right:1,center:1,block:1 },
                integrate = alignCommandIntegrator(editor);

            for (var value in align) {
                integrate(value);
            }
            if (typeof editor.config.cropduster_afterInit == 'function') {
                editor.config.cropduster_afterInit(editor);
            }
        }
    });

    // cropduster widget definition.
    var cropduster = {
        // Widget-specific rules for Allowed Content Filter.
        allowedContent: {
            // This widget may need <div> centering wrapper.
            div: {
                match: isCenterWrapper,
                styles: 'text-align'
            },
            figcaption: true,
            figure: {
                classes: '!caption',
                styles: 'float,display'
            },
            img: {
                attributes: '!src,alt,width,height',
                styles: 'float'
            },
            // This widget may need <p> centering wrapper.
            p: {
                match: isCenterWrapper,
                styles: 'text-align'
            }
        },

        // This widget converts style-driven dimensions to attributes.
        contentTransformations: [['img[width]: sizeToAttribute']],

        // This widget has an editable caption.
        editables: {
            caption: {
                selector: 'figcaption',
                allowedContent: 'br em strong sub sup u; a[!href]'
            }
        },

        parts: {
            image: 'img',
            caption: 'figcaption'
        },

        // The name of this widget's dialog.
        dialog: 'cropduster',

        // Template of the widget: plain image.
        template: template,

        data: function() {
            var widget = this,
                editor = widget.editor,
                oldState = widget.oldData,
                newState = widget.data;

            // Convert the internal form of the widget from the old state to the new one.
            widget.shiftState({
                element: widget.element,
                oldState: oldState,
                newState: newState,

                // Destroy the widget.
                destroy: function() {
                    if (this.destroyed) {
                        return;
                    }

                    // Remember whether widget was focused before destroyed.
                    if (editor.widgets.focused == widget) {
                        this.focused = true;
                    }

                    editor.widgets.destroy(widget);

                    // Mark widget was destroyed.
                    this.destroyed = true;
                },

                init: function(element) {
                    if (this.destroyed) {
                        // Create a new widget. This widget will be either captioned
                        // non-captioned, block or inline according to what is the
                        // new state of the widget.
                        widget = editor.widgets.initOn(element, 'cropduster', widget.data);
                        if (this.focused) {
                            // The focus must be transferred from the old one (destroyed)
                            // to the new one (just created).
                            widget.focus();
                            delete this.focused;
                        }
                        delete this.destroyed;
                    } else {
                        // If now widget was destroyed just update wrapper's alignment.
                        // According to the new state.
                        widget.setWrapperAlign();
                    }
                    if (typeof editor.config.cropduster_widgetStateInit == 'function') {
                        editor.config.cropduster_widgetStateInit.call(this, element, widget);
                    }
                }
            });

            widget.parts.image.setAttributes({
                src: widget.data.src,
                // This internal is required by the editor.
                'data-cke-saved-src': widget.data.src,
                alt: widget.data.alt
            });

            // Set dimensions of the image according to gathered data.
            setDimensions(widget);

            // Cache current data.
            widget.oldData = CKEDITOR.tools.extend({}, widget.data);
        },

        init: function() {
            var configVars = ['uploadTo', 'previewSize', 'url', 'urlParams', 'widgetConfig', 'initData'];
            this.config = {};
            for (var i = 0; i < configVars.length; i++) {
                var configVar = configVars[i];
                var key = 'cropduster_' + configVar;
                this.config[configVar] = this.editor.config[key];
            }

            var image = this.parts.image,
                imageSizeCss = {
                    width: CKEDITOR.tools.convertToPx(image.getStyle('width')),
                    height: CKEDITOR.tools.convertToPx(image.getStyle('height'))
                },
                data = {
                    hasCaption: !!this.parts.caption,
                    src: image.getAttribute('src'),
                    alt: image.getAttribute('alt') || '',
                    width: image.getAttribute('width') || imageSizeCss.width || '',
                    height: image.getAttribute('height') || imageSizeCss.height || '',
                    className: image.getAttribute('class') || ''
                };

            if (imageSizeCss.width) {
                image.setAttribute('width', image.getAttribute('width') || imageSizeCss.width);
            }
            if (imageSizeCss.height) {
                image.setAttribute('height', image.getAttribute('height') || imageSizeCss.height);
            }
            image.removeStyle('width');
            image.removeStyle('height');

            if (typeof this.config.initData == 'function') {
                data = this.config.initData(data, this);
            }

            // Read initial float style from figure/image and
            // then remove it. This style will be set on wrapper in #data listener.
            if (!data.align) {
                data.align = this.element.getStyle('float') || image.getStyle('float') || 'none';
                this.element.removeStyle('float');
                image.removeStyle('float');
            }

            // Get rid of extra vertical space when there's no caption.
            // It will improve the look of the resizer.
            if (!data.hasCaption) {
                this.wrapper.setStyle('line-height', '0');
            }

            this.setData(data);

            // Setup dynamic image resizing with mouse.
            setupResizer(this);

            this.shiftState = CKEDITOR.plugins.cropduster.stateShifter(this.editor);

            // Add widget editing option to its context menu.
            this.on('contextMenu', function(evt) {
                evt.data.cropduster = CKEDITOR.TRISTATE_OFF;
            });

            // Pass the reference to this widget to the dialog.
            this.on( 'dialog', function(evt) {
                evt.data.widget = this;
            }, this);
        },

        upcast: upcastWidgetElement,
        downcast: downcastWidgetElement,

        setWrapperAlign: function setWrapperAlign(widget) {
            var widget = this,
                wrapper = widget.wrapper,
                align = widget.data.align;

            if (align == 'center') {
                if (!widget.inline) {
                    wrapper.setStyle('text-align', 'center');
                }
                wrapper.removeStyle('float');
            } else {
                if (!widget.inline) {
                    wrapper.removeStyle('text-align');
                }
                if (align == 'none') {
                    wrapper.removeStyle('float');
                } else {
                    wrapper.setStyle('float', align);
                }
            }
        }
    };

    CKEDITOR.plugins.cropduster = CKEDITOR.plugins.cropduster || {};

    CKEDITOR.plugins.cropduster.stateShifter = function(editor) {
        // Tag name used for centering non-captioned widgets.
        var centerElement = editor.config.enterMode == CKEDITOR.ENTER_P ? 'p' : 'div',
            doc = editor.document,
            editable = editor.editable(),
            shiftables = ['hasCaption', 'align'], // The order that stateActions get executed. It matters!
            // Atomic procedures, one per state variable.
            stateActions = {
                align: function(data, oldValue, newValue) {
                    var hasCaptionAfter = data.newState.hasCaption,
                        element = data.element;

                    if (changed(data, 'align')) {
                        // Alignment changed.
                        if (!hasCaptionAfter) {
                            // No caption in the new state.
                            if (newValue == 'center') {
                                // Changed to "center" (non-captioned).
                                data.destroy();
                                data.element = wrapInCentering(element);
                            }
                            if (!changed(data, 'hasCaption') && oldValue == 'center' && newValue != 'center') {
                                // Changed to "non-center" from "center" while caption removed.
                                data.destroy();
                                data.element = unwrapFromCentering(element);
                            }
                        }
                    } else if (newValue == 'center' && changed(data, 'hasCaption') && !hasCaptionAfter) {
                        // Alignment remains and "center" removed caption.
                        data.destroy();
                        data.element = wrapInCentering(element);
                    }

                    // Finally set display for figure.
                    if (element.is('figure')) {
                        if (newValue == 'center') {
                            element.setStyle('display', 'inline-block');
                        } else {
                            element.removeStyle('display');
                        }
                    }
                },

                hasCaption: function(data, oldValue, newValue) {
                    // This action is for real state change only.
                    if (!changed(data, 'hasCaption')) {
                        return;
                    }

                    var element = data.element,
                        oldState = data.oldState,
                        newState = data.newState,
                        img;

                    // Switching hasCaption always destroys the widget.
                    data.destroy();

                    // There was no caption, but the caption is to be added.
                    if (newValue) {
                        // Get <img> from element. As element may be either
                        // <img> or centering <p>, consider it now.
                        img = element.findOne('img') || element;

                        // Create new <figure> from widget template.
                        var figure = CKEDITOR.dom.element.createFromHtml(templateBlock, doc);

                        // Replace element with <figure>.
                        replaceSafely(figure, element);

                        // Use old <img> instead of the one from the template,
                        // so we won't lose additional attributes.
                        img.replace(figure.findOne('img'));

                        // Update widget's element.
                        data.element = figure;
                    // The caption was present, but now it's to be removed.
                    } else {
                        // Unwrap <img> from figure.
                        img = element.findOne('img');
                        img.replace(element);
                        // Update widget's element.
                        data.element = img;
                    }
                }
            };

        function changed(data, name) {
            if (!data.oldState) {
                return false;
            } else {
                return data.oldState[name] !== data.newState[name];
            }
        }

        function wrapInCentering(element) {
            // When widget gets centered. Wrapper must be created.
            // Create new <p|div> with text-align:center.
            var center = doc.createElement(centerElement, {
                styles: { 'text-align': 'center' }
            });

            // Replace element with centering wrapper.
            replaceSafely(center, element);
            element.move(center);

            return center;
        }

        function unwrapFromCentering(element) {
            var img = element.findOne('img');
            img.replace(element);
            return img;
        }

        function replaceSafely(replacing, replaced) {
            if (replaced.getParent()) {
                var range = editor.createRange();

                // Move the range before old element and insert element into it.
                range.moveToPosition(replaced, CKEDITOR.POSITION_BEFORE_START);
                editable.insertElementIntoRange(replacing, range);

                // Remove old element.
                replaced.remove();
            }
            else {
                replacing.replace(replaced);
            }
        }

        return function(data) {
            if (typeof editor.config.cropduster_shiftables == 'object') {
                shiftables = editor.config.cropduster_shiftables;
            }

            var actions = CKEDITOR.tools.clone(stateActions);

            if (typeof editor.config.cropduster_stateActions == 'function') {
                var configActions = editor.config.cropduster_stateActions(editor);
                for (var k in configActions) {
                    actions[k] = configActions[k];
                }
            }

            var oldState = data.oldState,
                newState = data.newState,
                name;

            // Iterate over possible state variables.
            for (var i = 0; i < shiftables.length; i++) {
                name = shiftables[i];

                actions[name](data,
                    oldState ? oldState[name] : null,
                    newState[name]);
            }

            data.init(data.element);
        };
    };

    // Creates widgets from all <img> and <figure>.
    //
    // @param {CKEDITOR.htmlParser.element} el
    function upcastWidgetElement(el, data) {
        var dimensions = { width:1,height:1 },
            name = el.name,
            image;

        // If a center wrapper is found. So the element is:
        //         <div style="text-align:center"><figure>...</figure></div>.
        // Centering is done by widget.wrapper in such case. Hence, replace
        // centering wrapper with figure.
        // The other case is:
        //         <p style="text-align:center"><img></p>.
        // Then <p> takes charge of <figure> and nothing is to be changed.
        image = el.getFirst('img') || (el.getFirst('a') ? el.getFirst('a').getFirst('img') : null);
        if (isCenterWrapper(el)) {
            if (name == 'div') {
                var figure = el.getFirst('figure');
                el.replaceWith(figure);
                el = figure;
            }

            data.align = 'center';
        } else if (name == 'img') {
            image = el;
        }

        if (!image) {
            return;
        }

        // If there's an image, then cool, we got a widget.
        // Now just remove dimension attributes expressed with %.
        for (var d in dimensions) {
            var dimension = image.attributes[d];
            if (dimension && dimension.match(regexPercent)) {
                delete image.attributes[d];
            }
        }

        return el;
    }

    // Transforms the widget to the external format according to the current configuration.
    //
    // @param {CKEDITOR.htmlParser.element} el
    function downcastWidgetElement(el) {
        var attrs = el.attributes,
            align = this.data.align;

        // De-wrap the image from resize handle wrapper.
        // Only block widgets have one.
        if (!this.inline) {
            var resizeWrapper = el.getFirst('span'),
                img = resizeWrapper.getFirst('img');

            resizeWrapper.replaceWith(img);
        }

        if (align && align != 'none') {
            var styles = CKEDITOR.tools.parseCssText(attrs.style || '');

            // If centering, wrap downcasted element.
            // Wrappers for <img> and <figure> are <p> and <div>, respectively.
            if (align == 'center' && el.name != 'p') {
                var name = el.name == 'img' ? 'p' : 'div';

                el = el.wrapWith(new CKEDITOR.htmlParser.element(name, {
                    'style': 'text-align:center'
                }));
            }

            // If left/right, add float style to the downcasted element.
            else if (align in { left:1,right:1 })
                styles['float'] = align;

            // Update element styles.
            if (!CKEDITOR.tools.isEmpty(styles)) {
                attrs.style = CKEDITOR.tools.writeCssText(styles);
            }
        }

        return el;
    }

    function isCenterWrapper(el) {
        // Wrapper must be either <div> or <p>.
        if (!(el.name in { div:1,p:1 })) {
            return false;
        }

        var children = el.children;

        // Centering wrapper can have only one child.
        if (children.length !== 1) {
            return false;
        }

        var child = children[0],
            childName = child.name;

        // The only child of centering wrapper can be <figure> with
        // class="caption" or plain <img>.
        if (childName != 'img' && !(childName == 'figure' && (child.getFirst('img') || child.getFirst('a')))) {
            return false;
        }

        var styles = CKEDITOR.tools.parseCssText(el.attributes.style || '');

        // Centering wrapper got to be... centering.
        if (styles['text-align'] == 'center') {
            return true;
        }

        return false;
    }

    // Sets width and height of the widget image according to current widget data.
    //
    // @param {CKEDITOR.plugins.widget} widget
    function setDimensions(widget) {
        var data = widget.data,
            dimensions = { width: data.width, height: data.height },
            image = widget.parts.image;

        for (var d in dimensions) {
            if (dimensions[d]) {
                image.setAttribute(d, dimensions[d]);
            } else {
                image.removeAttribute(d);
            }
        }
    }

    // Defines all features related to drag-driven image resizing.
    //
    // @param {CKEDITOR.plugins.widget} widget
    function setupResizer(widget) {
        var editor = widget.editor,
            editable = editor.editable(),
            doc = editor.document,
            resizer = doc.createElement('span');

        resizer.addClass('cke_cropduster_resizer');
        resizer.setAttribute('title', editor.lang.cropduster.resizer);
        resizer.append(new CKEDITOR.dom.text('\u200b', doc));

        // Inline widgets don't need a resizer wrapper as an image spans the entire widget.
        if (!widget.inline) {
            var oldResizeWrapper = widget.element.findOne('span'),
                resizeWrapper = doc.createElement('span');

            resizeWrapper.addClass('cke_cropduster_resizer_wrapper');
            resizeWrapper.append(widget.parts.image.clone());
            resizeWrapper.replace(widget.parts.image);
            resizeWrapper.append(resizer);
            widget.parts.image = resizeWrapper.findOne('img');

            // Remove the old wrapper which could came from e.g. pasted HTML
            // and which could be corrupted (e.g. resizer span has been lost).
            if (oldResizeWrapper) {
                resizeWrapper.replace(oldResizeWrapper);
            }
        } else {
            widget.wrapper.append(resizer);
        }

        // Calculate values of size variables and mouse offsets.
        resizer.on('mousedown', function(evt) {
            var image = widget.parts.image,

                // "factor" can be either 1 or -1. I.e.: For right-aligned images, we need to
                // subtract the difference to get proper width, etc. Without "factor",
                // resizer starts working the opposite way.
                factor = widget.data.align == 'right' ? -1 : 1,

                // The x-coordinate of the mouse relative to the screen
                // when button gets pressed.
                startX = evt.data.$.screenX,
                startY = evt.data.$.screenY,

                // The initial dimensions and aspect ratio of the image.
                startWidth = image.$.clientWidth,
                startHeight = image.$.clientHeight,
                ratio = startWidth / startHeight,

                listeners = [],

                // A class applied to editable during resizing.
                cursorClass = 'cke_cropduster_s' + (!~factor ? 'w' : 'e'),

                nativeEvt, newWidth, newHeight, updateData,
                moveDiffX, moveDiffY, moveRatio;

            // Save the undo snapshot first: before resizing.
            editor.fire('saveSnapshot');

            // Mousemove listeners are removed on mouseup.
            attachToDocuments('mousemove', onMouseMove, listeners);

            // Clean up the mousemove listener. Update widget data if valid.
            attachToDocuments('mouseup', onMouseUp, listeners);

            // The entire editable will have the special cursor while resizing goes on.
            editable.addClass(cursorClass);

            // This is to always keep the resizer element visible while resizing.
            resizer.addClass('cke_cropduster_resizing');

            // Attaches an event to a global document if inline editor.
            // Additionally, if framed, also attaches the same event to iframe's document.
            function attachToDocuments(name, callback, collection) {
                var globalDoc = CKEDITOR.document,
                    listeners = [];

                if (!doc.equals(globalDoc)) {
                    listeners.push(globalDoc.on(name, callback));
                }

                listeners.push(doc.on(name, callback));

                if (collection) {
                    for (var i = listeners.length; i--;) {
                        collection.push(listeners.pop());
                    }
                }
            }

            // Calculate with first, and then adjust height, preserving ratio.
            function adjustToX() {
                newWidth = startWidth + factor * moveDiffX;
                newHeight = 0 | newWidth / ratio;
            }

            // Calculate height first, and then adjust width, preserving ratio.
            function adjustToY() {
                newHeight = startHeight - moveDiffY;
                newWidth = 0 | newHeight * ratio;
            }

            // This is how variables refer to the geometry.
            // Note: x corresponds to moveOffset, this is the position of mouse
            // Note: o corresponds to [startX, startY].
            //
            //     +--------------+--------------+
            //     |              |              |
            //     |      I       |      II      |
            //     |              |              |
            //     +------------- o -------------+ _ _ _
            //     |              |              |      ^
            //     |      VI      |     III      |      | moveDiffY
            //     |              |         x _ _ _ _ _ v
            //     +--------------+---------|----+
            //                    |         |
            //                     <------->
            //                     moveDiffX
            function onMouseMove(evt) {
                nativeEvt = evt.data.$;

                // This is how far the mouse is from the point the button was pressed.
                moveDiffX = nativeEvt.screenX - startX;
                moveDiffY = startY - nativeEvt.screenY;

                // This is the aspect ratio of the move difference.
                moveRatio = Math.abs(moveDiffX / moveDiffY);

                // Left, center or none-aligned widget.
                if (factor == 1) {
                    if (moveDiffX <= 0) {
                        // Case: IV.
                        if (moveDiffY <= 0) {
                            adjustToX();
                        // Case: I.
                        } else {
                            if (moveRatio >= ratio) {
                                adjustToX();
                            } else {
                                adjustToY();
                            }
                        }
                    } else {
                        // Case: III.
                        if (moveDiffY <= 0) {
                            if (moveRatio >= ratio) {
                                adjustToY();
                            } else {
                                adjustToX();
                            }
                        // Case: II.
                        } else {
                            adjustToY();
                        }
                    }
                }

                // Right-aligned widget. It mirrors behaviours, so I becomes II,
                // IV becomes III and vice-versa.
                else {
                    if (moveDiffX <= 0) {
                        // Case: IV.
                        if (moveDiffY <= 0) {
                            if (moveRatio >= ratio) {
                                adjustToY();
                            } else {
                                adjustToX();
                            }
                        // Case: I.
                        } else {
                            adjustToY();
                        }
                    } else {
                        // Case: III.
                        if (moveDiffY <= 0) {
                            adjustToX();
                        // Case: II.
                        } else {
                            if (moveRatio >= ratio) {
                                adjustToX();
                            } else {
                                adjustToY();
                            }
                        }
                    }
                }

                // Don't update attributes if less than 10.
                // This is to prevent images to visually disappear.
                if (newWidth >= 15 && newHeight >= 15) {
                    image.setAttributes({ width: newWidth, height: newHeight });
                    updateData = true;
                } else
                    updateData = false;
            }

            function onMouseUp(evt) {
                var l;

                while ((l = listeners.pop()))
                    l.removeListener();

                if (updateData) {
                    widget.setData({ width: newWidth, height: newHeight });

                    // Save another undo snapshot: after resizing.
                    editor.fire('saveSnapshot');
                }

                // Restore default cursor by removing special class.
                editable.removeClass(cursorClass);

                // This is to bring back the regular behaviour of the resizer.
                resizer.removeClass('cke_cropduster_resizing');

                // Don't update data twice or more.
                updateData = false;
            }
        });

        // Change the position of the widget resizer when data changes.
        widget.on('data', function() {
            resizer[widget.data.align == 'right' ? 'addClass' : 'removeClass']('cke_cropduster_resizer_left');
        });
    }

    // Integrates widget alignment setting with justify
    // plugin's commands (execution and refreshment).
    // @param {CKEDITOR.editor} editor
    // @param {String} value 'left', 'right', 'center' or 'block'
    function alignCommandIntegrator(editor) {
        var execCallbacks = [];

        return function(value) {
            var command = editor.getCommand('justify' + value);

            // Most likely, the justify plugin isn't loaded.
            if (!command) {
                return;
            }

            // This command will be manually refreshed along with
            // other commands after exec.
            execCallbacks.push(function() {
                command.refresh(editor, editor.elementPath());
            });

            if (value in { right:1,left:1,center:1 }) {
                command.on('exec', function(evt) {
                    var widget = getFocusedWidget(editor);

                    if (widget) {
                        widget.setData('align', value);

                        // Once the widget changed its align, all the align commands
                        // must be refreshed: the event is to be cancelled.
                        for (var i = execCallbacks.length; i--;) {
                            execCallbacks[i]();
                        }

                        evt.cancel();
                    }
                });
            }

            command.on('refresh', function(evt) {
                var widget = getFocusedWidget(editor),
                    allowed = { right:1,left:1,center:1 };

                if (!widget) {
                    return;
                }

                this.setState(
                    (widget.data.align == value)
                      ? CKEDITOR.TRISTATE_ON
                      : (value in allowed) ? CKEDITOR.TRISTATE_OFF : CKEDITOR.TRISTATE_DISABLED);

                evt.cancel();
            });
        };
    }

    // Returns the focused widget, if of the type specific for this plugin.
    // If no widget is focused, `null` is returned.
    //
    // @param {CKEDITOR.editor}
    // @returns {CKEDITOR.plugins.widget}
    function getFocusedWidget(editor) {
        var widget = editor.widgets.focused;
        return (widget && widget.name == 'cropduster') ? widget : null;
    }
})();