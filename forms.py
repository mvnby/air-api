from wtforms import Field, widgets

class TagListField(Field):
    widget = widgets.TextInput()

    def _value(self):
        if self.data:
            return ", ".join(self.data)
        return ""

    def process_formdata(self, valuelist):
        if valuelist:
            self.data = [x.strip() for x in valuelist[0].split(",") if x.strip()]
        else:
            self.data = []
