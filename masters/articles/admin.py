from django.contrib import admin
from models import *

class ArticleAdmin(admin.ModelAdmin):
    model = models.Article

admin.site.register(models.Article, ArticleAdmin)
