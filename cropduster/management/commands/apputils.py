import os.path
get_def_file = lambda s, o: os.path.abspath(inspect.getfile(o))

def find_django_models(module):
    """
    Returns all django models defined within a module.  It attempts this
    by iterating through the module's contents and finding subclasses
    of the Django base model.

    @param module: Python Module
    @type  module: Python Module

    @return: Set of Django Model Classes
    @rtype: [Class1, ...]
    """
    cur_file = get_def_file(module)
    classes = []
    for obj in module.__dict__.itervalues():
        # We check the definition file for each object to make sure we
        # only grab local models, not imports.
        if isinstance(obj, ModelBase) and cur_file == get_def_file(obj):
            classes.append(obj)

    return classes

def find_cropduster_images(model):
    """
    Dives into a model to find Cropduster images.

    TODO:  Find if there's a cleaner way to do this.

    @param model: Model to introspect. 
    @type  model: Class 

    @return: Set of cropduster image fields.
    @rtype:  ["field1", ...]
    """
    fields = []
    for field in model._meta.fields:
        if isinstance(field, CropDusterImage) or isinstance(field, CDF):
            fields.append(field.name)
        # We also need to handle m2m, o2m, m2o relationships
        elif field.rel is not None and field.rel.to is CropDusterImage:
            fields.append(field.name)

    return fields

def import_app(app_name, model_name=None, field_name=None):
    """
    Imports an app and figures out which models and fields are Cropduster 
    Images

    @param app_name: Name of the app, as known by its path
    @type  app_name: "name" 
    
    @param model_name: Specific model to use or None to look at all models.
    @type  model_name: "Model Name" or None
    
    @param field_name: Specific field on a model or None to look at all 
                       fields. 
    @type  field_name: "field name" or None

    @return: set of field names by model
    @rtype: [(Model1, ["field1", ...])]
    """
    # Attempt to import
    module = __import__(app_name, globals(), locals(), ['models']).models

    # if we have a specific model, use only that particular one.
    if model_name is not None:
        models = [ getattr(module, model_name) ]

    else:
        # Attempt to introspect the module
        models = find_django_models(module)

    # Find all the relevant field(s)
    if field_name is not None:
        field_map = [(models[0], [ field_name ])]
    else:
        # Otherwise, more introspection!
        field_map = []
        for model in models:
            field_map.append((model, find_cropduster_images(model)))

    return field_map

def resolve_apps(apps):
    """
    Takes a couple of raw apps and converts them into sets of Models/fields.

    @param apps: set of apps
    @type  apps: <"app[:model[.field]]", ...>

    @return: Set of models, fields
    @rtype: [(Model1, ["field1", ...]), ...]
    """
    for app_name in apps:
        field_name = model_name = None
        if ':' in app_name:
            if '.' in app_name and app_name.index('.') > app_name.index(':'):
                app_name, field_name = app_name.rsplit('.', 1)
            app_name, model_name = app_name.split(':', 1)

        for model, fields in import_app(app_name, model_name, field_name):
            if fields:
                yield model, fields

