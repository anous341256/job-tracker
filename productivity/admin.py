from django.contrib import admin

from .models import Communication, Contact, Document, Resume, Tag

admin.site.register(Contact)
admin.site.register(Resume)
admin.site.register(Document)
admin.site.register(Communication)
admin.site.register(Tag)
