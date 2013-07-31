(function($) {

    /*
      Generates a new random attr id since we can never guarantee that
      the actual form id isn't changed via javascript.
    */
    var setup_attr_id = function($container) {
        var input_id = $container.find('input.cropduster').attr('id');
        var random_attr_id = Math.floor(Math.random() * 0xFFFFFFFF);
        var attr_id = input_id + random_attr_id;
        $container.find('[data-attr_id]').attr('data-attr_id', attr_id);
        return attr_id;
    };

    window.cropduster_pop = function(upload_url, id, size_set_id, image_id, image_hash){

        var query_char = (upload_url.indexOf('?') > -1) ? '&' : '?';

        var href = upload_url + query_char + 'pop=1' +
                    '&size_set=' + size_set_id +
                    '&image_element_id=' + id +
                    '&image_hash=' + image_hash;

        var $input = $("div.cropduster_input[data-attr_id=" + id + "] input");
        if ($input.val() != ''){
            image_id = $input.val();
        }

        if (image_id !== undefined){
            href += '&image_id=' + image_id;
        }

        window.open(href, id, 'height=650, width=960, resizable=yes, scrollbars=yes');

        return false;
    };

    window.toggle_delete = function(obj){
        var $container = $(obj).parent().parent().parent().parent();
        
        $container.toggleClass("predelete");

        var $input = $(container).find("input.cropduster");
        // Swap the title and the value fields, that way the values can be swapped back if deletion is canceled
        var tempValue = $input.val();
        var tempTitle = $input.attr("title");

        $input.val(tempTitle);
        $input.attr("title", tempValue);

        return false;
    };
    window.show_cropduster = function(e) {
        var $this = $(this);
        var upload_url = $this.attr('href');
        var attr_id = $this.attr('data-attr_id');
        if (attr_id.length === 0) {
            attr_id = setup_attr_id($this.parent().parent());
        }
        var size_set_id = $this.attr('data-size_set_id');

        var orig_image = $('div[data-attr_id="'+attr_id+'"] img.original').attr('data-image_id');
        var image_hash = $this.attr('data-image_hash');

        // Show the popup
        cropduster_pop(upload_url, attr_id, size_set_id, orig_image, image_hash);
        return false;
    };

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

    // jsrender templates for complete.html
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

})((typeof window.django == 'object') ? django.jQuery : jQuery);