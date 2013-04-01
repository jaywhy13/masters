# Create your views here.
from django.http import HttpResponse
from django.template import RequestContext 
from django.shortcuts import get_object_or_404, render_to_response
from models import *


def preview_article(request, id):
	obj = get_object_or_404(Article, pk=id)
	return render_to_response("preview_article.html", context_instance=RequestContext(request, dict(article=obj)))

def review(request, id, model=None, json_name=None, template_name=None):
	""" Returns the next article that we can verify the references for
	"""
	obj = get_object_or_404(model, pk=id)
	ctx = {json_name:obj}
	print "Returning context for review: %s" % ctx
	return render_to_response(template_name, context_instance=RequestContext(request, ctx))

def update_reference(request, id, action="confirm"):
	article_reference = get_object_or_404(ArticleReference, pk=id)
	if action == "confirm":
		article_reference.confirmed = True
		article_reference.valid = True
		article_reference.save()
	elif action == "remove":
		article_reference.confirmed = True
		article_reference.save()
	return HttpResponse("success")

def close_article(request, id):
	article = get_object_or_404(Article, pk=id)
	article.reviewed = True
	article.save()
	return HttpResponse("success")

def reference_context(request, id):
	article_reference = get_object_or_404(ArticleReference, pk=id)
	return render_to_response('reference_context.html', context_instance=RequestContext(request, dict(article_reference=article_reference)))

def article_statistics(request):
	article_count = Article.objects.filter(reviewed=True).count()
	confirmed_reference_count = ArticleReference.objects.filter(confirmed=True).count()
	return HttpResponse("%s articles closed, %s references confirmed" % (article_count, confirmed_reference_count))

