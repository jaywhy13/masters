from django.conf.urls import patterns, include, url
from views import review, update_reference, close_article, preview_article, reference_context, article_statistics
from django.views.generic.simple import direct_to_template
from models import *

urlpatterns = patterns('',
	url(r'preview_article/id/(?P<id>\d+)$', preview_article, name='preview-article'),
    url(r'review_article/id/(?P<id>\d+)$', review, {'model':Article, 'json_name':'article', 'template_name' : 'article.html'}, name='review-article' ),
    url(r'close_article/id/(?P<id>\d+)$', close_article, name='close-article'),
    url(r'statistics$', article_statistics, name='article-statistics'),
    # References...
    url(r'review_reference/id/(?P<id>\d+)$', review, {'model':ArticleReference, 'json_name':'article_reference', 'template_name': 'article_reference.html'}, name='review-reference'),
    url(r'confirm_reference/id/(?P<id>\d+)$', update_reference, {'action' : 'confirm'}, name='confirm-reference'),
    url(r'remove_reference/id/(?P<id>\d+)$', update_reference, {'action' : 'remove'}, name='remove-reference'),
    url(r'reference_context/id/(?P<id>\d+)$', reference_context, name='reference-context')
)
