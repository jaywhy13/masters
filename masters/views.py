from django.http import HttpResponse
from django.shortcuts import render_to_response
from django.template import RequestContext

from masters.articles.models import Article, ArticleReference, TrainingSet

def home(request):
	article_reference_id = request.GET.get("article_reference_id", None)
	article_id = request.GET.get("article_id", None)
	training_set_id = request.GET.get("training_set_id", None)

	if training_set_id:
		(training_set, created) = TrainingSet.objects.get_or_create(pk=training_set_id)
		total_in_training_set = training_set.articles.count()

	if article_reference_id:
		print "Got an id here"
		article_id = ArticleReference.objects.get(pk=article_reference_id).article.pk
	return render_to_response("index.html", context_instance=RequestContext(request, locals()))
