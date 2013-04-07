from django.contrib import admin
import models

class ArticleReferenceInline(admin.TabularInline):
	model = models.ArticleReference

class ArticleAdmin(admin.ModelAdmin):
    model = models.Article
    search_fields = ['title', 'body']
    inlines = [ ArticleReferenceInline ]

class ArticleReferenceAdmin(admin.ModelAdmin):
	model = models.ArticleReference
	search_fields = ['gazetteer__name', 'article__title', 'article__body']
	list_display = ['confirmed', 'article', 'gazetteer', 'sentence', 'position_in_sentence', 'valid']
	ordering = ['confirmed', 'valid', 'gazetteer__name']

	def sentence(self, model):
		return model.sentence


admin.site.register(models.Article, ArticleAdmin)
admin.site.register(models.ArticleReference, ArticleReferenceAdmin)