from wtforms import Field, widgets

class TagListField(Field):
    widget = widgets.TextInput()
    
    def __init__(self, *args, **kwargs):
        # SQLAdmin injects relationship args that Field doesn't understand
        kwargs.pop('allow_blank', None)
        kwargs.pop('query_factory', None)
        kwargs.pop('data', None)
        super().__init__(*args, **kwargs)

    def _value(self):
        if self.data:
            names = []
            for item in self.data:
                names.append(item.name if hasattr(item, 'name') else str(item))
            return ", ".join(names)
        return ""

    def process_formdata(self, valuelist):
        if valuelist:
            self.data = [x.strip() for x in valuelist[0].split(",") if x.strip()]
        else:
            self.data = []

    def populate_obj(self, obj, name):
        pass
