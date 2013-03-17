from django.contrib import admin
import models

class ArticleAdmin(admin.ModelAdmin):
    model = models.Article

admin.site.register(models.Article, ArticleAdmin)
