from django import forms


def apply_date_picker_widgets(fields):
    """Apply browser-native date controls consistently across the project."""
    for field in fields.values():
        existing_class = field.widget.attrs.get('class', '')
        if isinstance(field, forms.DateTimeField):
            field.widget = forms.DateTimeInput(
                format='%Y-%m-%dT%H:%M',
                attrs={'type': 'datetime-local', 'class': existing_class},
            )
            if '%Y-%m-%dT%H:%M' not in field.input_formats:
                field.input_formats = ['%Y-%m-%dT%H:%M', *field.input_formats]
        elif isinstance(field, forms.DateField):
            field.widget = forms.DateInput(
                format='%Y-%m-%d',
                attrs={'type': 'date', 'class': existing_class},
            )
